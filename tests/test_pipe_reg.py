"""M1 smoke test: random traffic with backpressure through pipe_reg.

Timing convention used by every testbench in this project:
  - Drive inputs right after a rising edge.
  - Sample handshakes at the falling edge.
Nothing changes between the falling edge and the next rising edge, so the
sampled values are exactly what the DUT sees at that rising edge.
"""

import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge
from cocotb_tools.runner import get_runner

PROJ = Path(__file__).resolve().parents[1]
N_ITEMS = 500


async def reset(dut, cycles=5):
    dut.rst_n.value = 0
    dut.in_valid.value = 0
    dut.out_ready.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def drive(dut, items, idle_prob=0.3):
    """Send items with random idle gaps. Hold valid/data until accepted."""
    for item in items:
        while random.random() < idle_prob:
            dut.in_valid.value = 0
            await RisingEdge(dut.clk)
        dut.in_valid.value = 1
        dut.in_data.value = item
        while True:
            await FallingEdge(dut.clk)
            accepted = dut.in_ready.value == 1
            await RisingEdge(dut.clk)
            if accepted:
                break
    dut.in_valid.value = 0


async def backpressure(dut, ready_prob=0.7):
    while True:
        dut.out_ready.value = int(random.random() < ready_prob)
        await RisingEdge(dut.clk)


async def monitor(dut, received):
    while True:
        await FallingEdge(dut.clk)
        if dut.out_valid.value == 1 and dut.out_ready.value == 1:
            received.append(dut.out_data.value.to_unsigned())


@cocotb.test()
async def random_traffic(dut):
    Clock(dut.clk, 10, unit="ns").start()
    await reset(dut)

    width = len(dut.in_data)
    items = [random.getrandbits(width) for _ in range(N_ITEMS)]
    received = []

    cocotb.start_soon(monitor(dut, received))
    cocotb.start_soon(backpressure(dut))
    await drive(dut, items)

    for _ in range(100):
        if len(received) == len(items):
            break
        await RisingEdge(dut.clk)

    assert received == items, f"sent {len(items)}, received {len(received)}"


def test_pipe_reg():
    """pytest entry point: build with Verilator and run the cocotb tests above."""
    runner = get_runner("verilator")
    runner.build(
        sources=[PROJ / "rtl" / "pipe_reg.sv"],
        hdl_toplevel="pipe_reg",
        parameters={"W": 16},
        build_dir=PROJ / "sim_build" / "pipe_reg",
        always=True,
    )
    runner.test(
        hdl_toplevel="pipe_reg",
        test_module="test_pipe_reg",
        build_dir=PROJ / "sim_build" / "pipe_reg",
    )


if __name__ == "__main__":
    test_pipe_reg()
