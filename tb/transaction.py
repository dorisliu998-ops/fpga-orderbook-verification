"""Transaction types: the data passed between testbench components.

What this file defines:
  - Parameters (bit widths, table size) copied from docs/design-spec.md.
  - Enums for every encoded field (message type, side, event type, error code).
  - Message: one input message sent to the DUT.
  - Event:   one output event produced by the DUT (or predicted by the model).

Who uses it:
  Driver          turns a Message into DUT input signals.
  Input monitor   turns accepted DUT inputs back into a Message.
  Reference model takes a Message and returns the expected Event.
  Output monitor  turns DUT output signals into an Event.
  Scoreboard      compares expected Event == actual Event.

Similar to a uvm_sequence_item in UVM.
"""

from dataclasses import dataclass
from enum import IntEnum

# ----------------------------------------------------------------------------
# Parameters (must match the RTL and docs/design-spec.md)
# ----------------------------------------------------------------------------

ID_W = 16  # order_id width in bits
PRICE_W = 16  # price width in bits (unit = $0.01)
QTY_W = 16  # quantity width in bits
MAX_ORDERS = 64  # order table capacity

# ----------------------------------------------------------------------------
# Field encodings. IntEnum = an int with a name, like an SV enum.
# MsgType.ADD == 0 is True, and it prints as "MsgType.ADD" in logs.
# ----------------------------------------------------------------------------


class MsgType(IntEnum):
    """Encoding of in_msg_type."""

    ADD = 0
    CANCEL = 1
    EXECUTE = 2
    RESERVED = 3  # not a valid type; DUT must reject with BAD_TYPE


class Side(IntEnum):
    """Encoding of in_side / out_side."""

    BUY = 0
    SELL = 1


class EventType(IntEnum):
    """Encoding of out_event."""

    ADDED = 0
    CANCELED = 1
    EXECUTED = 2  # partial fill, order stays in the book
    FILLED = 3  # full fill, order removed
    REJECT = 4  # message had an error, book unchanged


class ErrCode(IntEnum):
    """Encoding of out_err. Valid only when out_event == REJECT."""

    NONE = 0
    BAD_TYPE = 1
    BAD_QTY = 2
    BAD_PRICE = 3
    DUP_ID = 4
    UNKNOWN_ID = 5
    BOOK_FULL = 6
    QTY_UNDERFLOW = 7


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _check_fits_in_bits(name, value, width):
    """Raise ValueError if value does not fit in an unsigned field of `width` bits.

    Valid range is 0 .. 2**width - 1. (1 << width) is 2**width.
    """
    if not 0 <= value < (1 << width):
        raise ValueError(f"{name}={value} does not fit in {width} bits")


# ----------------------------------------------------------------------------
# Message: one input to the DUT
# ----------------------------------------------------------------------------


# @dataclass auto-generates __init__ (constructor), __repr__ (printing) and
# __eq__ (field-by-field ==). frozen=True makes fields read-only after creation.
# The "name: type" lines are required: @dataclass uses them to find the fields.
@dataclass(frozen=True)
class Message:
    """One input message. Fields are the DUT input signals.

    Fields a message type does not use are don't-care (CANCEL ignores side,
    price and qty; EXECUTE ignores side and price). They default to 0.
    """

    msg_type: MsgType  # required
    order_id: int  # required
    side: Side = Side.BUY  # ADD only
    price: int = 0  # ADD only
    qty: int = 0  # ADD and EXECUTE

    def __post_init__(self):
        """Called automatically right after the generated __init__.

        Rejects values that cannot exist on the DUT's wires (e.g. qty=70000 on a
        16-bit bus). Those are testbench bugs. Values like qty=0 are legal wire
        values and are DUT error cases, so they are allowed here.
        """
        _check_fits_in_bits("order_id", self.order_id, ID_W)
        _check_fits_in_bits("price", self.price, PRICE_W)
        _check_fits_in_bits("qty", self.qty, QTY_W)

    # Shortcut constructors. @staticmethod is Python's version of C++ `static`:
    # call through the class, no object needed, e.g. Message.add(...).
    # Each one fills in msg_type and sets fields by name, so a value cannot
    # land in the wrong field by position.

    @staticmethod
    def add(order_id, side, price, qty):
        """Create an ADD message: insert a new order."""
        return Message(msg_type=MsgType.ADD, order_id=order_id, side=side, price=price, qty=qty)

    @staticmethod
    def cancel(order_id):
        """Create a CANCEL message: remove an order."""
        return Message(msg_type=MsgType.CANCEL, order_id=order_id)

    @staticmethod
    def execute(order_id, qty):
        """Create an EXECUTE message: fill `qty` of an existing order."""
        return Message(msg_type=MsgType.EXECUTE, order_id=order_id, qty=qty)


# ----------------------------------------------------------------------------
# Event: one output from the DUT
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """One output event. Fields are the DUT output signals.

    side and price come from the stored order. qty is the quantity change
    (see docs/design-spec.md). For REJECT, side/price/qty are 0 and err is set.
    """

    event: EventType
    order_id: int
    side: Side = Side.BUY
    price: int = 0
    qty: int = 0
    err: ErrCode = ErrCode.NONE

    @staticmethod
    def reject(order_id, err):
        """Create a REJECT event with the given error code."""
        return Event(event=EventType.REJECT, order_id=order_id, err=err)
