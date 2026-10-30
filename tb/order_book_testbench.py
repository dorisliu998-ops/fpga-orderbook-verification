"""The complete order book testbench: every component, created and connected.

Why this file exists:
  Every test needs the same setup: a driver, two monitors, a scoreboard,
  a clock and a reset. Putting that here means each test only has to say
  which messages to send.

How the pieces are connected:

    test ──messages──> driver ──> DUT ──> output monitor ──actual──┐
                                   │                                ▼
                            input monitor ──accepted──> scoreboard (reference model inside)

Typical use inside a cocotb test:

    testbench = OrderBookTestbench(dut)
    await testbench.start()
    await testbench.send_and_check([Message.add(...), Message.cancel(...)])
"""

from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from tb.order_book_driver import OrderBookDriver
from tb.order_book_input_monitor import OrderBookInputMonitor
from tb.order_book_output_monitor import OrderBookOutputMonitor
from tb.order_book_scoreboard import OrderBookScoreboard


class OrderBookTestbench:
    """Creates and connects the driver, both monitors and the scoreboard."""

    def __init__(self, dut, idle_probability=0.0):
        """Create every component. Nothing runs until start() is called.

        idle_probability is passed to the driver (chance of an idle cycle
        before each message).
        """
        self.dut = dut
        self.scoreboard = OrderBookScoreboard(dut._log)
        self.driver = OrderBookDriver(dut, idle_probability)
        self.input_monitor = OrderBookInputMonitor(dut, self.scoreboard)
        self.output_monitor = OrderBookOutputMonitor(dut, self.scoreboard)

    async def start(self):
        """Start the clock and both monitors, then reset the DUT.

        The downstream is always ready (out_ready = 1) for now.
        """
        Clock(self.dut.clk, 10, unit="ns").start()
        self.dut.out_ready.value = 1
        self.input_monitor.start()
        self.output_monitor.start()
        await self.reset_dut()

    async def reset_dut(self, cycles=3):
        """Hold rst_n low for `cycles` clock cycles, then release it."""
        self.dut.rst_n.value = 0
        await ClockCycles(self.dut.clk, cycles)
        self.dut.rst_n.value = 1
        await RisingEdge(self.dut.clk)

    async def wait_until_all_events_checked(self, max_cycles=2000):
        """Wait until every expected event has come out of the DUT (or max_cycles pass)."""
        for _ in range(max_cycles):
            if self.scoreboard.pending_count() == 0:
                break
            await RisingEdge(self.dut.clk)
        # A few more cycles so any extra, unexpected event also shows up
        await ClockCycles(self.dut.clk, 10)

    async def send_and_check(self, messages):
        """Send every message, wait for the DUT to finish, then run the end-of-test checks."""
        await self.driver.send_all(messages)
        await self.wait_until_all_events_checked()
        self.scoreboard.check_end_of_test()
