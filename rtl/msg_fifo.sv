`timescale 1ns / 1ps

// msg_fifo: synchronous FIFO with ready/valid on both sides.
//
// Buffers input messages so a burst can arrive faster than the order book
// engine consumes them. Each entry holds one complete message.
//
// Behavior:
//   - in_ready is low when the FIFO is full, unless an entry is being read
//     in the same cycle (then a write can take the freed entry).
//   - out_valid is high whenever the FIFO is not empty; out_data is the
//     oldest entry (show-ahead, no read latency).
//   - Synchronous active-low reset empties the FIFO. While rst_n is low,
//     in_ready and out_valid are both 0.
//
// DEPTH must be a power of 2 so the pointers wrap naturally.
module msg_fifo #(
    parameter int WIDTH = 51,  // bits per entry
    parameter int DEPTH = 16   // number of entries (power of 2)
) (
    input  logic             clk,
    input  logic             rst_n,

    // Write side
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [WIDTH-1:0] in_data,

    // Read side
    output logic             out_valid,
    input  logic             out_ready,
    output logic [WIDTH-1:0] out_data
);

    localparam int PTR_W = $clog2(DEPTH);

    logic [WIDTH-1:0] entries [DEPTH];
    logic [PTR_W-1:0] write_ptr;   // next entry to write
    logic [PTR_W-1:0] read_ptr;    // oldest entry
    logic [PTR_W:0]   used_count;  // number of entries in use, 0..DEPTH

    logic is_full;
    logic is_empty;
    logic do_write;
    logic do_read;

    assign is_full  = (used_count == DEPTH[PTR_W:0]);
    assign is_empty = (used_count == '0);

    assign out_valid = rst_n && !is_empty;
    assign out_data  = entries[read_ptr];
    assign do_read   = out_valid && out_ready;

    // Accept a write when there is room, or when an entry is leaving this cycle.
    assign in_ready = rst_n && (!is_full || do_read);
    assign do_write = in_valid && in_ready;

    // Pointers and count
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            write_ptr  <= '0;
            read_ptr   <= '0;
            used_count <= '0;
        end else begin
            if (do_write) write_ptr <= write_ptr + 1'b1;
            if (do_read)  read_ptr  <= read_ptr + 1'b1;

            case ({do_write, do_read})
                2'b10:   used_count <= used_count + 1'b1;
                2'b01:   used_count <= used_count - 1'b1;
                default: ;  // no change, or one in and one out
            endcase
        end
    end

    // Storage. No reset needed for data.
    always_ff @(posedge clk) begin
        if (do_write && !is_full) begin
            entries[write_ptr] <= in_data;
        end
    end

endmodule
