"""Main testbench for rtl/order_book_top.sv. Grows step by step through M4.

Tests so far:
  M4.1  driver_sends_all_messages
          driver only; checks every message is accepted.
  M4.2  add_execute_cancel_give_expected_events
          driver + output monitor; expected events written by hand.
  M4.3  scoreboard_* tests
          full testbench (tb/order_book_testbench.py): the reference model
          predicts every expected event and the scoreboard checks them.
          A test only lists the messages to send.

Run: pytest -v -s tests/test_order_book.py
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, with_timeout
from cocotb_tools.runner import get_runner

from tb.order_book_driver import OrderBookDriver
from tb.order_book_output_monitor import OrderBookOutputMonitor
from tb.order_book_testbench import OrderBookTestbench
from tb.transaction import ErrCode, Event, EventType, Message, MsgType, Side

PROJ = Path(__file__).resolve().parents[1]  # repo root


async def start_clock_and_reset(dut):
    """Start a 10 ns clock and hold reset for 3 cycles.

    Inputs must already be idle (OrderBookDriver sets them in its constructor).
    out_ready is set to 1: the downstream is always ready in this step.
    """
    Clock(dut.clk, 10, unit="ns").start()
    dut.out_ready.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def driver_sends_all_messages(dut):
    """The driver delivers every message (each one gets accepted by the DUT)."""
    driver = OrderBookDriver(dut, idle_probability=0.3)
    await start_clock_and_reset(dut)

    messages = [
        Message.add(101, Side.BUY, 15000, 100),
        Message.add(102, Side.SELL, 15002, 300),
        Message.execute(101, 40),
        Message.cancel(102),
    ]

    # If the handshake logic is wrong, send_all may never return.
    # with_timeout turns that hang into a clear failure after 1 us.
    await with_timeout(driver.send_all(messages), 1, "us")

    dut._log.info("driver sent %d messages", len(messages))


@cocotb.test()
async def add_execute_cancel_give_expected_events(dut):
    """Two ADDs, a partial EXECUTE and a CANCEL. Check every output event field."""
    driver = OrderBookDriver(dut, idle_probability=0.3)
    output_monitor = OrderBookOutputMonitor(dut)
    await start_clock_and_reset(dut)
    output_monitor.start()

    messages = [
        Message.add(101, Side.BUY, 15000, 100),
        Message.add(102, Side.SELL, 15002, 300),
        Message.execute(101, 40),
        Message.cancel(102),
    ]

    # Expected events, written by hand from docs/design-spec.md
    expected_events = [
        Event(event=EventType.ADDED, order_id=101, side=Side.BUY, price=15000, qty=100, err=ErrCode.NONE),
        Event(event=EventType.ADDED, order_id=102, side=Side.SELL, price=15002, qty=300, err=ErrCode.NONE),
        Event(event=EventType.EXECUTED, order_id=101, side=Side.BUY, price=15000, qty=40, err=ErrCode.NONE),
        Event(event=EventType.CANCELED, order_id=102, side=Side.SELL, price=15002, qty=300, err=ErrCode.NONE),
    ]

    await driver.send_all(messages)
    await output_monitor.wait_for_event_count(len(expected_events))
    await ClockCycles(dut.clk, 10)  # give any extra (wrong) events time to show up

    for event in output_monitor.received_events:
        dut._log.info("got %s", event)

    assert len(output_monitor.received_events) == len(expected_events), "wrong number of events"
    for index in range(len(expected_events)):
        actual = output_monitor.received_events[index]
        expected = expected_events[index]
        assert actual == expected, f"event {index}: expected {expected}, got {actual}"


# ============================================================================
# M4.3: full testbench. Expected events come from the reference model.
# ============================================================================


@cocotb.test()
async def scoreboard_add_execute_cancel(dut):
    """Same messages as the M4.2 test, but checked by the scoreboard."""
    testbench = OrderBookTestbench(dut, idle_probability=0.3)
    await testbench.start()

    await testbench.send_and_check(
        [
            Message.add(101, Side.BUY, 15000, 100),
            Message.add(102, Side.SELL, 15002, 300),
            Message.execute(101, 40),
            Message.cancel(102),
        ]
    )


@cocotb.test()
async def scoreboard_every_error_once(dut):
    """Trigger each error code on its own (except BOOK_FULL, which needs 64 orders)."""
    testbench = OrderBookTestbench(dut)
    await testbench.start()

    await testbench.send_and_check(
        [
            Message(msg_type=MsgType.RESERVED, order_id=1),  # BAD_TYPE
            Message.add(2, Side.BUY, 100, 0),  # BAD_QTY
            Message.add(3, Side.BUY, 0, 10),  # BAD_PRICE
            Message.add(4, Side.BUY, 100, 10),  # valid, sets up the next ones
            Message.add(4, Side.SELL, 200, 20),  # DUP_ID
            Message.cancel(5),  # UNKNOWN_ID
            Message.execute(4, 11),  # QTY_UNDERFLOW (only 10 left)
        ]
    )


def test_order_book():
    """pytest entry point: build the order book RTL and run every @cocotb.test() above."""
    build_dir = PROJ / "sim_build" / "order_book"
    runner = get_runner("verilator")
    runner.build(
        sources=[PROJ / "rtl" / "msg_fifo.sv", PROJ / "rtl" / "order_book_top.sv"],
        hdl_toplevel="order_book_top",
        build_dir=build_dir,
        always=True,
    )
    runner.test(
        hdl_toplevel="order_book_top",
        test_module="test_order_book",
        build_dir=build_dir,
    )


if __name__ == "__main__":
    test_order_book()
