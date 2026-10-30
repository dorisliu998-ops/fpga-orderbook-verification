"""Output monitor for the order book DUT.

What a monitor does:
  Watches signals and records what happened. It never drives anything.
  This one watches the output port and records every event the DUT hands
  to the downstream, as Event objects (tb/transaction.py).

When an event counts as delivered (docs/design-spec.md, Handshake Rules):
  On a rising edge where out_valid == 1 and out_ready == 1, and the DUT is
  not in reset. We sample at the falling edge before that rising edge:
  nothing changes in between, so the values we read are exactly what the
  downstream receives at the edge.

How it runs:
  start() launches watch_output_port() in the background with
  cocotb.start_soon. It keeps running alongside the test (like an SV
  fork ... join_none) until the simulation ends.
"""

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

from tb.transaction import ErrCode, Event, EventType, Side


class OrderBookOutputMonitor:
    """Records every event delivered on the DUT output port."""

    def __init__(self, dut):
        """Store the DUT handle. received_events starts empty."""
        self.dut = dut
        self.received_events = []  # list of Event, in the order they came out

    def start(self):
        """Start watching in the background. Returns immediately."""
        cocotb.start_soon(self.watch_output_port())

    async def watch_output_port(self):
        """Forever: at each falling edge, record the event if a handshake will happen."""
        while True:
            await FallingEdge(self.dut.clk)
            # TODO (exercise 1): decide whether an event is delivered at the
            # next rising edge. If so, read it with
            # self.read_event_from_output_signals() and append it to
            # self.received_events.
            # Conditions: out_valid is 1, out_ready is 1, and rst_n is 1.
            # Remember .value when reading a signal.
            raise NotImplementedError("TODO: watch_output_port")

    def read_event_from_output_signals(self):
        """Build an Event from the current values of the out_* signals. Takes no time."""
        # TODO (exercise 2): read the six out_* data signals and return
        #   Event(event=..., order_id=..., side=..., price=..., qty=..., err=...)
        # Reading values:
        #   multi-bit signal: self.dut.out_price.value.to_unsigned()
        #   1-bit signal:     int(self.dut.out_side.value)
        # Wrap encoded fields in their enum: EventType(...), Side(...), ErrCode(...)
        raise NotImplementedError("TODO: read_event_from_output_signals")

    async def wait_for_event_count(self, expected_count, max_cycles=1000):
        """Wait until at least expected_count events have been recorded.

        Fails the test if that does not happen within max_cycles clock cycles.
        """
        for _ in range(max_cycles):
            if len(self.received_events) >= expected_count:
                return
            await RisingEdge(self.dut.clk)
        raise AssertionError(
            f"expected {expected_count} events, got {len(self.received_events)} after {max_cycles} cycles"
        )
