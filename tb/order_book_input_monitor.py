"""Input monitor for the order book DUT.

What it does:
  Watches the input port and reports every message the DUT actually
  accepted to the scoreboard. It never drives anything.

Why not just trust the driver:
  The driver knows what it tried to send, not what the DUT received. If the
  driver has a bug, or a message is offered during reset, the two differ.
  The reference model must see exactly what the DUT saw, so it is fed from
  this monitor, which watches the wires independently.

When a message counts as accepted (docs/design-spec.md, Handshake Rules):
  On a rising edge where in_valid == 1 and in_ready == 1, and rst_n == 1.
  We sample at the falling edge before that rising edge.

Reset:
  While rst_n is 0, it calls scoreboard.on_reset() every cycle, so the
  reference model is cleared exactly when the DUT is.
"""

import cocotb
from cocotb.triggers import FallingEdge

from tb.transaction import Message, MsgType, Side


class OrderBookInputMonitor:
    """Reports every accepted input message (and every reset cycle) to the scoreboard."""

    def __init__(self, dut, scoreboard):
        """Store the DUT handle and the scoreboard to report to."""
        self.dut = dut
        self.scoreboard = scoreboard
        self.accepted_messages = []  # every accepted message, kept for debugging

    def start(self):
        """Start watching in the background. Returns immediately."""
        cocotb.start_soon(self.watch_input_port())

    async def watch_input_port(self):
        """Forever: at each falling edge, report a reset or an accepted message."""
        while True:
            await FallingEdge(self.dut.clk)

            if self.dut.rst_n.value == 0:
                self.scoreboard.on_reset()
                continue  # skip the rest of this loop iteration

            handshake = self.dut.in_valid.value == 1 and self.dut.in_ready.value == 1
            if handshake:
                message = self.read_message_from_input_signals()
                self.accepted_messages.append(message)
                self.scoreboard.on_message_accepted(message)

    def read_message_from_input_signals(self):
        """Build a Message from the current values of the in_* signals. Takes no time."""
        return Message(
            msg_type=MsgType(self.dut.in_msg_type.value.to_unsigned()),
            order_id=self.dut.in_order_id.value.to_unsigned(),
            side=Side(int(self.dut.in_side.value)),
            price=self.dut.in_price.value.to_unsigned(),
            qty=self.dut.in_qty.value.to_unsigned(),
        )
