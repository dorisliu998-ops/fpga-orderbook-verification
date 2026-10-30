"""Driver for the order book DUT's input interface.

What a driver does:
  Takes Message objects (tb/transaction.py) and turns them into signal
  activity on the DUT inputs, following the ready/valid protocol.
  It only "does"; it does not check anything. Checking is the job of the
  monitors and the scoreboard.

Protocol it must follow (docs/design-spec.md, Handshake Rules):
  - Put the message on the in_* data signals and raise in_valid.
  - Keep in_valid and the data unchanged until a rising edge where
    in_ready is 1. That edge is the transfer.
  - Only then move on to the next message (or drop in_valid).

Timing convention (same as every test in this project):
  - Change signals right after a rising edge.
  - Read signals at the falling edge.
"""

import random

from cocotb.triggers import FallingEdge, RisingEdge


class OrderBookDriver:
    """Sends Message objects into the DUT input port."""

    def __init__(self, dut, idle_probability=0.0):
        """Store the DUT handle and set all inputs to idle.

        idle_probability: chance (0.0 to 1.0) of inserting one idle cycle
        (in_valid = 0) before each message. 0.0 means send back to back.
        """
        self.dut = dut
        self.idle_probability = idle_probability
        self.set_inputs_idle()

    def set_inputs_idle(self):
        """Drive in_valid low and every data field to 0. Takes no time."""
        self.dut.in_valid.value = 0
        self.dut.in_msg_type.value = 0
        self.dut.in_order_id.value = 0
        self.dut.in_side.value = 0
        self.dut.in_price.value = 0
        self.dut.in_qty.value = 0

    def put_message_on_bus(self, message):
        """Drive one message's fields onto the in_* signals and raise in_valid. Takes no time."""
        # TODO (exercise 1): set in_valid to 1, and copy the 5 fields of
        # `message` onto in_msg_type, in_order_id, in_side, in_price, in_qty.
        # Hint: look at set_inputs_idle() above. Enums need int(...).
        #msg_type: MsgType  # required
        #order_id: int  # required
        #side: Side = Side.BUY  # ADD only
        #price: int = 0  # ADD only
        #qty: int = 0  # ADD and EXECUTE
        self.dut.in_valid.value =  1
        self.dut.in_msg_type.value = message.msg_type
        self.dut.in_order_id.value = message.order_id
        self.dut.in_side.value = message.side
        self.dut.in_price.value = message.price
        self.dut.in_qty.value = message.qty

    async def send(self, message):
        """Send one message and return once the DUT has accepted it.

        Call this right after a rising edge. Returns right after the rising
        edge on which the transfer happened.
        """
        # Optional random idle cycles before this message
        while random.random() < self.idle_probability:
            self.dut.in_valid.value = 0
            await RisingEdge(self.dut.clk)

        self.put_message_on_bus(message)

        # Wait for the handshake: in_ready must be 1 at a rising edge.
        # TODO (exercise 2): loop until the message is accepted.
        #   Each cycle: wait for the falling edge, read in_ready,
        #   then wait for the rising edge. Stop after the rising edge
        #   where in_ready was 1.
        # Hint: the smoke test (tests/test_order_book_smoke.py) has this loop.
        while True:
            await FallingEdge(self.dut.clk)
            if_accepted = self.dut.in_ready.value
            await RisingEdge(self.dut.clk)
            if if_accepted == 1:
                self.dut.in_valid.value = 0
                break



    async def send_all(self, messages):
        """Send every message in the list, in order."""
        for message in messages:
            await self.send(message)
