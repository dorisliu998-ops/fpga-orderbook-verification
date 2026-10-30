"""Smoke test for rtl/order_book_top.sv.

Purpose: prove the order book RTL builds and can process one message.
Sends a single ADD and checks the DUT outputs one ADDED event with the
same fields. It does NOT check anything else; real verification is your
testbench (M4 onward).

Uses the same timing convention as test_pipe_reg.py:
drive right after a rising edge, sample at the falling edge.

Run: pytest -v tests/test_order_book_smoke.py
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge
from cocotb_tools.runner import get_runner

PROJ = Path(__file__).resolve().parents[1]  # repo root


async def reset_dut(dut):
    """Hold reset for 3 cycles with every input at 0, then release."""
    dut.rst_n.value = 0
    dut.in_valid.value = 0
    dut.in_msg_type.value = 0
    dut.in_order_id.value = 0
    dut.in_side.value = 0
    dut.in_price.value = 0
    dut.in_qty.value = 0
    dut.out_ready.value = 1  # downstream always ready in this test
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def one_add_gives_one_added_event(dut):
    """Send ADD 101 BUY 15000 x100. Expect exactly one ADDED event with the same fields."""
    Clock(dut.clk, 10, unit="ns").start()
    await reset_dut(dut)

    # Drive one ADD and hold it until the DUT accepts it (in_ready = 1)
    dut.in_valid.value = 1
    dut.in_msg_type.value = 0  # ADD
    dut.in_order_id.value = 101
    dut.in_side.value = 0  # BUY
    dut.in_price.value = 15000
    dut.in_qty.value = 100
    while True:
        await FallingEdge(dut.clk)
        accepted = dut.in_ready.value == 1
        await RisingEdge(dut.clk)
        if accepted:
            break
    dut.in_valid.value = 0

    # Wait for the output event (give up after 20 cycles)
    got_event = False
    for _ in range(20):
        await FallingEdge(dut.clk)
        if dut.out_valid.value == 1:
            got_event = True
            break
    assert got_event, "no output event within 20 cycles"

    # Note: 1-bit signals read back as a Logic value; use int() to compare.
    assert dut.out_event.value.to_unsigned() == 0, "expected ADDED (0)"
    assert dut.out_order_id.value.to_unsigned() == 101
    assert int(dut.out_side.value) == 0
    assert dut.out_price.value.to_unsigned() == 15000
    assert dut.out_qty.value.to_unsigned() == 100
    assert dut.out_err.value.to_unsigned() == 0

    # Exactly one event: nothing else should come out
    for _ in range(10):
        await FallingEdge(dut.clk)
        assert dut.out_valid.value == 0, "unexpected extra output event"


def test_order_book_smoke():
    """pytest entry point: build the order book RTL with Verilator and run the test above."""
    build_dir = PROJ / "sim_build" / "order_book_smoke"
    runner = get_runner("verilator")
    runner.build(
        sources=[PROJ / "rtl" / "msg_fifo.sv", PROJ / "rtl" / "order_book_top.sv"],
        hdl_toplevel="order_book_top",
        build_dir=build_dir,
        always=True,
    )
    runner.test(
        hdl_toplevel="order_book_top",
        test_module="test_order_book_smoke",
        build_dir=build_dir,
    )


if __name__ == "__main__":
    test_order_book_smoke()
