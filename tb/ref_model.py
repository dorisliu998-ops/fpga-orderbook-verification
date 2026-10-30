"""Reference model (golden model) of the order book.

What it does:
  Keeps its own copy of the order book. For each input message it
    1. updates the book, exactly as the spec says the DUT must, and
    2. returns the event the DUT is expected to output.
  The scoreboard compares that expected event with the DUT's actual output.

How it is written:
  - From docs/design-spec.md only, never from the RTL. If the model copied
    the RTL's approach, both could share the same bug and nothing would
    catch it.
  - Orders are kept in a Python dict keyed by order_id. The RTL will use 64
    table slots, but which slot holds which order is an implementation detail
    the spec does not define, so the model does not track slots.
"""

from dataclasses import dataclass

from tb.transaction import MAX_ORDERS, ErrCode, Event, EventType, MsgType, Side


@dataclass
class Order:
    """One resting order in the book.

    Not frozen: `remaining` must be changed in place when an EXECUTE partially
    fills the order.
    """

    side: Side
    price: int
    remaining: int  # quantity not yet filled


class OrderBookModel:
    """The model's order book plus the rules for updating it."""

    def __init__(self, max_orders=MAX_ORDERS):
        """Start with an empty book.

        max_orders can be lowered in tests so BOOK_FULL is easy to reach.
        """
        self.max_orders = max_orders
        self.orders = {}  # dict: order_id -> Order

    def reset(self):
        """Empty the book. Called when the DUT is reset."""
        self.orders.clear()

    def __len__(self):
        """Number of active orders. Lets callers write len(book)."""
        return len(self.orders)

    def update_book(self, msg):
        """Apply one input message to the book. Return the expected output event.

        Step 1: look for an error. Any error -> book unchanged, return REJECT.
        Step 2: no error -> change the book and return the matching event.
        """
        # Step 1: errors
        err = self._find_error(msg)
        if err is not ErrCode.NONE:
            return Event.reject(msg.order_id, err)

        # Step 2: valid message
        order_id = msg.order_id

        if msg.msg_type is MsgType.ADD:
            # Insert the new order. Event echoes the message fields.
            self.orders[order_id] = Order(msg.side, msg.price, msg.qty)
            return Event(EventType.ADDED, order_id, msg.side, msg.price, msg.qty)

        if msg.msg_type is MsgType.CANCEL:
            # Remove the order. Event reports the stored side/price and the
            # quantity that was still resting.
            order = self.orders.pop(order_id)
            return Event(EventType.CANCELED, order_id, order.side, order.price, order.remaining)

        # Only EXECUTE is left (RESERVED was already rejected as BAD_TYPE).
        # The order must exist: otherwise _find_error returned UNKNOWN_ID.
        order = self.orders[order_id]
        if msg.qty == order.remaining:
            # Full fill: remove the order.
            del self.orders[order_id]
            return Event(EventType.FILLED, order_id, order.side, order.price, msg.qty)
        # Partial fill: reduce remaining, order stays.
        order.remaining -= msg.qty
        return Event(EventType.EXECUTED, order_id, order.side, order.price, msg.qty)

    def _find_error(self, msg):
        """Return the highest-priority error for msg, or ErrCode.NONE if valid.

        Does not change the book. Checks run in spec priority order and the
        first match wins:
          stateless (fields only): BAD_TYPE > BAD_QTY > BAD_PRICE
          stateful (needs book):   DUP_ID / UNKNOWN_ID > BOOK_FULL > QTY_UNDERFLOW
        The leading underscore marks it as internal to this class.
        """
        msg_type = msg.msg_type
        id_in_book = msg.order_id in self.orders

        # Stateless checks
        if msg_type is MsgType.RESERVED:
            return ErrCode.BAD_TYPE
        if msg_type in (MsgType.ADD, MsgType.EXECUTE) and msg.qty == 0:
            return ErrCode.BAD_QTY
        if msg_type is MsgType.ADD and msg.price == 0:
            return ErrCode.BAD_PRICE

        # Stateful checks
        if msg_type is MsgType.ADD and id_in_book:
            return ErrCode.DUP_ID
        if msg_type in (MsgType.CANCEL, MsgType.EXECUTE) and not id_in_book:
            return ErrCode.UNKNOWN_ID
        if msg_type is MsgType.ADD and len(self.orders) >= self.max_orders:
            return ErrCode.BOOK_FULL
        if msg_type is MsgType.EXECUTE and msg.qty > self.orders[msg.order_id].remaining:
            return ErrCode.QTY_UNDERFLOW

        return ErrCode.NONE
