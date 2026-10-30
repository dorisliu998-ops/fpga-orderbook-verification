`timescale 1ns / 1ps

// order_book_top: market data feed handler, v1 (structured input).
//
// Implements docs/design-spec.md:
//   input messages -> msg_fifo -> lookup + error check + book update -> output event register
//
// Pipeline:
//   1. Accepted messages are stored in msg_fifo.
//   2. The engine looks at the oldest message. In the same cycle it
//        - searches the order table for the message's order_id,
//        - finds a free slot (for ADD),
//        - decides the error code (if any) and the output event.
//   3. When the output register can take a new event, the engine "fires":
//      the message is removed from the FIFO, the order table is updated,
//      and the event is loaded into the output register.
//   One message is processed per cycle at most.
//
// Order table: MAX_ORDERS slots. Each slot holds valid, order_id, side,
// price and remaining quantity. Lookup by order_id compares all slots in
// parallel (CAM-style).
module order_book_top #(
    parameter int MAX_ORDERS = 64,
    parameter int FIFO_DEPTH = 16
) (
    input  logic        clk,
    input  logic        rst_n,      // synchronous, active-low

    // Input messages (ready/valid)
    input  logic        in_valid,
    output logic        in_ready,
    input  logic [1:0]  in_msg_type,
    input  logic [15:0] in_order_id,
    input  logic        in_side,
    input  logic [15:0] in_price,
    input  logic [15:0] in_qty,

    // Output events (ready/valid)
    output logic        out_valid,
    input  logic        out_ready,
    output logic [2:0]  out_event,
    output logic [15:0] out_order_id,
    output logic        out_side,
    output logic [15:0] out_price,
    output logic [15:0] out_qty,
    output logic [2:0]  out_err
);

    // ------------------------------------------------------------------
    // Encodings (must match docs/design-spec.md and tb/transaction.py)
    // ------------------------------------------------------------------
    localparam logic [1:0] MSG_ADD      = 2'd0;
    localparam logic [1:0] MSG_CANCEL   = 2'd1;
    localparam logic [1:0] MSG_EXECUTE  = 2'd2;

    localparam logic [2:0] EV_ADDED     = 3'd0;
    localparam logic [2:0] EV_CANCELED  = 3'd1;
    localparam logic [2:0] EV_EXECUTED  = 3'd2;
    localparam logic [2:0] EV_FILLED    = 3'd3;
    localparam logic [2:0] EV_REJECT    = 3'd4;

    localparam logic [2:0] ERR_NONE          = 3'd0;
    localparam logic [2:0] ERR_BAD_TYPE      = 3'd1;
    localparam logic [2:0] ERR_BAD_QTY       = 3'd2;
    localparam logic [2:0] ERR_BAD_PRICE     = 3'd3;
    localparam logic [2:0] ERR_DUP_ID        = 3'd4;
    localparam logic [2:0] ERR_UNKNOWN_ID    = 3'd5;
    localparam logic [2:0] ERR_BOOK_FULL     = 3'd6;
    localparam logic [2:0] ERR_QTY_UNDERFLOW = 3'd7;

    localparam int MSG_W  = 2 + 16 + 1 + 16 + 16;  // 51 bits per FIFO entry
    localparam int SLOT_W = $clog2(MAX_ORDERS);    // bits to index a slot

    // ------------------------------------------------------------------
    // Input FIFO
    // ------------------------------------------------------------------
    logic             fifo_out_valid;
    logic [MSG_W-1:0] fifo_out_data;
    logic             output_stage_free;  // output register can take a new event
    logic             engine_fire;        // process the oldest message this cycle

    msg_fifo #(
        .WIDTH (MSG_W),
        .DEPTH (FIFO_DEPTH)
    ) u_msg_fifo (
        .clk       (clk),
        .rst_n     (rst_n),
        .in_valid  (in_valid),
        .in_ready  (in_ready),
        .in_data   ({in_msg_type, in_order_id, in_side, in_price, in_qty}),
        .out_valid (fifo_out_valid),
        .out_ready (output_stage_free),
        .out_data  (fifo_out_data)
    );

    // Fields of the message at the head of the FIFO
    logic [1:0]  msg_type;
    logic [15:0] msg_order_id;
    logic        msg_side;
    logic [15:0] msg_price;
    logic [15:0] msg_qty;

    assign {msg_type, msg_order_id, msg_side, msg_price, msg_qty} = fifo_out_data;

    logic is_add;
    logic is_cancel;
    logic is_execute;

    assign is_add     = (msg_type == MSG_ADD);
    assign is_cancel  = (msg_type == MSG_CANCEL);
    assign is_execute = (msg_type == MSG_EXECUTE);

    // ------------------------------------------------------------------
    // Order table
    // ------------------------------------------------------------------
    logic [MAX_ORDERS-1:0] slot_valid;
    logic [15:0]           slot_order_id  [MAX_ORDERS];
    logic                  slot_side      [MAX_ORDERS];
    logic [15:0]           slot_price     [MAX_ORDERS];
    logic [15:0]           slot_remaining [MAX_ORDERS];
    logic [SLOT_W:0]       active_order_count;  // 0..MAX_ORDERS

    // Lookup: which slot (if any) holds msg_order_id
    logic              id_found;
    logic [SLOT_W-1:0] found_slot;

    always_comb begin
        id_found   = 1'b0;
        found_slot = '0;
        for (int i = 0; i < MAX_ORDERS; i++) begin
            if (slot_valid[i] && slot_order_id[i] == msg_order_id) begin
                id_found   = 1'b1;
                found_slot = SLOT_W'(i);
            end
        end
    end

    // Free slot search: lowest-numbered empty slot, used by ADD
    localparam int LAST_SLOT = MAX_ORDERS - 1;

    logic              free_slot_found;
    logic [SLOT_W-1:0] free_slot;

    always_comb begin
        free_slot_found = 1'b0;
        free_slot       = '0;
        for (int i = 0; i < LAST_SLOT; i++) begin
            if (!slot_valid[i] && !free_slot_found) begin
                free_slot_found = 1'b1;
                free_slot       = SLOT_W'(i);
            end
        end
    end

    logic book_full;
    assign book_full = (active_order_count == (SLOT_W + 1)'(MAX_ORDERS));

    // Stored fields of the found order
    logic        found_side;
    logic [15:0] found_price;
    logic [15:0] found_remaining;

    assign found_side      = slot_side[found_slot];
    assign found_price     = slot_price[found_slot];
    assign found_remaining = slot_remaining[found_slot];

    // ------------------------------------------------------------------
    // Error check
    // ------------------------------------------------------------------
    logic [2:0] error_code;

    always_comb begin
        if (!is_add && !is_cancel && !is_execute)
            error_code = ERR_BAD_TYPE;
        else if (is_add && id_found)
            error_code = ERR_DUP_ID;
        else if ((is_cancel || is_execute) && !id_found)
            error_code = ERR_UNKNOWN_ID;
        else if ((is_add || is_execute) && msg_qty == '0)
            error_code = ERR_BAD_QTY;
        else if (is_add && msg_price == '0)
            error_code = ERR_BAD_PRICE;
        else if (is_add && book_full)
            error_code = ERR_BOOK_FULL;
        else if (is_execute && msg_qty > found_remaining)
            error_code = ERR_QTY_UNDERFLOW;
        else
            error_code = ERR_NONE;
    end

    logic msg_ok;
    logic is_full_fill;

    assign msg_ok       = (error_code == ERR_NONE);
    assign is_full_fill = is_execute && (msg_qty == found_remaining);

    // ------------------------------------------------------------------
    // Output event for the current message
    // ------------------------------------------------------------------
    logic [2:0]  next_event;
    logic        next_side;
    logic [15:0] next_price;
    logic [15:0] next_qty;

    always_comb begin
        // Default: REJECT with zeroed side/price/qty
        next_event = EV_REJECT;
        next_side  = 1'b0;
        next_price = '0;
        next_qty   = '0;

        if (msg_ok) begin
            if (is_add) begin
                next_event = EV_ADDED;
                next_side  = msg_side;
                next_price = msg_price;
                next_qty   = msg_qty;
            end else if (is_cancel) begin
                next_event = EV_CANCELED;
                next_side  = found_side;
                next_price = found_price;
                next_qty   = found_remaining;    // quantity removed from the book
            end else begin  // EXECUTE
                next_event = is_full_fill ? EV_FILLED : EV_EXECUTED;
                next_side  = found_side;
                next_price = found_price;
                next_qty   = is_full_fill ? msg_qty : found_remaining - msg_qty;
            end
        end
    end

    // ------------------------------------------------------------------
    // Fire: process one message when there is one and the output can take it
    // ------------------------------------------------------------------
    logic out_valid_q;

    assign output_stage_free = !out_valid_q || out_ready;
    assign engine_fire       = fifo_out_valid && output_stage_free;

    // ------------------------------------------------------------------
    // Order table update
    // ------------------------------------------------------------------

    // Valid bits: cleared by reset
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            slot_valid <= '0;
        end else if (engine_fire && msg_ok) begin
            if (is_add)
                slot_valid[free_slot] <= 1'b1;
            else if (is_cancel || is_full_fill)
                slot_valid[found_slot] <= 1'b0;
        end
    end

    // Slot contents: only meaningful when the slot is valid, so no reset
    always_ff @(posedge clk) begin
        if (engine_fire && msg_ok) begin
            if (is_add) begin
                slot_order_id[free_slot]  <= msg_order_id;
                slot_side[free_slot]      <= msg_side;
                slot_price[free_slot]     <= msg_price;
                slot_remaining[free_slot] <= msg_qty;
            end else if (is_execute) begin
                slot_remaining[found_slot] <= found_remaining - msg_qty;
            end
        end
    end

    // Number of active orders
    always_ff @(posedge clk) begin
        if (engine_fire && msg_ok) begin
            if (is_add)
                active_order_count <= active_order_count + 1'b1;
            else if (is_cancel || is_full_fill)
                active_order_count <= active_order_count - 1'b1;
        end
    end

    // ------------------------------------------------------------------
    // Output register
    // ------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            out_valid_q <= 1'b0;
        end else if (output_stage_free) begin
            out_valid_q <= engine_fire;
        end
    end

    always_ff @(posedge clk) begin
        if (engine_fire) begin
            out_event    <= next_event;
            out_order_id <= msg_order_id;
            out_side     <= next_side;
            out_price    <= next_price;
            out_qty      <= next_qty;
            out_err      <= error_code;
        end
    end

    assign out_valid = rst_n && out_valid_q;

endmodule
