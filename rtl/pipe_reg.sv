`timescale 1ns / 1ps

// One-stage ready/valid pipeline register.
// Used in M1 to bring up the toolchain; reused later as an output stage.
module pipe_reg #(
    parameter int W = 16
) (
    input  logic         clk,
    input  logic         rst_n,

    input  logic         in_valid,
    output logic         in_ready,
    input  logic [W-1:0] in_data,

    output logic         out_valid,
    input  logic         out_ready,
    output logic [W-1:0] out_data
);

    // Accept when the register is empty or is being drained this cycle.
    assign in_ready = rst_n && (!out_valid || out_ready);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
        end else if (in_ready) begin
            out_valid <= in_valid;
        end
    end

    always_ff @(posedge clk) begin
        if (in_valid && in_ready) begin
            out_data <= in_data;
        end
    end

endmodule
