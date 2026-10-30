"""Unit tests for the reference model (tb/ref_model.py).

Pure Python: no cocotb, no simulator. Runs in milliseconds.

Why test the model at all: the scoreboard trusts the model as the definition
of "correct". A bug here would either flag a correct DUT or hide a DUT bug
that matches it. So the model is checked against the spec first.

How pytest works here:
  - Every function whose name starts with test_ is one test. pytest finds and
    runs them automatically.
  - Each test builds its own empty OrderBookModel, so tests never affect
    each other.
  - assert checks a condition. If it is False, the test fails and pytest
    prints both sides.

Run: pytest -v tests/test_ref_model.py
"""

import pytest

from tb.ref_model import OrderBookModel
from tb.transaction import ErrCode, Event, EventType, Message, MsgType, Side

# ============================================================================
# Normal flow
# ============================================================================


def test_add():
    """A valid ADD inserts the order and echoes its fields."""
    book = OrderBookModel()

    event = book.update_book(Message.add(101, Side.BUY, 15000, 100))

    expected = Event(event=EventType.ADDED, order_id=101, side=Side.BUY, price=15000, qty=100)
    assert event == expected
    assert len(book) == 1


def test_cancel_reports_stored_side_price_and_remaining():
    """CANCEL reports side/price from the book and the quantity still resting."""
    book = OrderBookModel()
    book.update_book(Message.add(101, Side.SELL, 15002, 300))
    book.update_book(Message.execute(101, 100))  # 200 left

    event = book.update_book(Message.cancel(101))

    expected = Event(event=EventType.CANCELED, order_id=101, side=Side.SELL, price=15002, qty=200)
    assert event == expected
    assert len(book) == 0


def test_partial_execute():
    """EXECUTE below remaining reduces remaining and keeps the order."""
    book = OrderBookModel()
    book.update_book(Message.add(101, Side.BUY, 15000, 100))

    event = book.update_book(Message.execute(101, 40))

    expected = Event(event=EventType.EXECUTED, order_id=101, side=Side.BUY, price=15000, qty=40)
    assert event == expected
    assert book.orders[101].remaining == 60


def test_full_execute_removes_order():
    """EXECUTE equal to remaining produces FILLED and removes the order."""
    book = OrderBookModel()
    book.update_book(Message.add(101, Side.BUY, 15000, 100))
    book.update_book(Message.execute(101, 40))  # 60 left

    event = book.update_book(Message.execute(101, 60))

    expected = Event(event=EventType.FILLED, order_id=101, side=Side.BUY, price=15000, qty=60)
    assert event == expected
    assert 101 not in book.orders


# ============================================================================
# Each error on its own
# ============================================================================


def test_error_bad_type():
    """msg_type 3 (RESERVED) is rejected with BAD_TYPE."""
    book = OrderBookModel()

    event = book.update_book(Message(msg_type=MsgType.RESERVED, order_id=1))

    assert event == Event.reject(1, ErrCode.BAD_TYPE)


def test_error_bad_qty_on_add():
    """ADD with qty 0 is rejected with BAD_QTY."""
    book = OrderBookModel()

    event = book.update_book(Message.add(1, Side.BUY, 100, 0))

    assert event == Event.reject(1, ErrCode.BAD_QTY)


def test_error_bad_qty_on_execute():
    """EXECUTE with qty 0 is rejected with BAD_QTY."""
    book = OrderBookModel()
    book.update_book(Message.add(1, Side.BUY, 100, 10))

    event = book.update_book(Message.execute(1, 0))

    assert event == Event.reject(1, ErrCode.BAD_QTY)


def test_error_bad_price():
    """ADD with price 0 is rejected with BAD_PRICE."""
    book = OrderBookModel()

    event = book.update_book(Message.add(1, Side.BUY, 0, 10))

    assert event == Event.reject(1, ErrCode.BAD_PRICE)


def test_error_duplicate_id():
    """ADD with an ID already in the book is rejected with DUP_ID."""
    book = OrderBookModel()
    book.update_book(Message.add(1, Side.BUY, 100, 10))

    event = book.update_book(Message.add(1, Side.SELL, 200, 20))

    assert event == Event.reject(1, ErrCode.DUP_ID)


def test_error_unknown_id_on_cancel():
    """CANCEL of an ID not in the book is rejected with UNKNOWN_ID."""
    book = OrderBookModel()

    event = book.update_book(Message.cancel(1))

    assert event == Event.reject(1, ErrCode.UNKNOWN_ID)


def test_error_unknown_id_on_execute():
    """EXECUTE of an ID not in the book is rejected with UNKNOWN_ID."""
    book = OrderBookModel()

    event = book.update_book(Message.execute(1, 5))

    assert event == Event.reject(1, ErrCode.UNKNOWN_ID)


def test_error_qty_underflow():
    """EXECUTE for more than the remaining quantity is rejected with QTY_UNDERFLOW."""
    book = OrderBookModel()
    book.update_book(Message.add(1, Side.BUY, 100, 10))

    event = book.update_book(Message.execute(1, 11))

    assert event == Event.reject(1, ErrCode.QTY_UNDERFLOW)


def test_error_book_full():
    """ADD when the book is full is rejected with BOOK_FULL.

    Uses a 4-entry book so the test does not need 64 ADDs.
    """
    book = OrderBookModel(max_orders=4)
    book.update_book(Message.add(1, Side.BUY, 100, 10))
    book.update_book(Message.add(2, Side.BUY, 100, 10))
    book.update_book(Message.add(3, Side.BUY, 100, 10))
    book.update_book(Message.add(4, Side.BUY, 100, 10))

    event = book.update_book(Message.add(5, Side.BUY, 100, 10))

    assert event == Event.reject(5, ErrCode.BOOK_FULL)
    assert len(book) == 4


# ============================================================================
# Spec invariants
# ============================================================================


def test_reject_does_not_change_book():
    """Spec invariant 3: a REJECT never changes the book.

    Send several bad messages, then check order 1 is exactly as it was.
    """
    book = OrderBookModel()
    book.update_book(Message.add(1, Side.BUY, 100, 10))

    book.update_book(Message.add(1, Side.SELL, 200, 20))  # DUP_ID
    book.update_book(Message.execute(1, 11))  # QTY_UNDERFLOW
    book.update_book(Message.cancel(2))  # UNKNOWN_ID

    assert len(book) == 1
    assert book.orders[1].side == Side.BUY
    assert book.orders[1].price == 100
    assert book.orders[1].remaining == 10


def test_cancel_ignores_unused_fields():
    """CANCEL must ignore side/price/qty even if they hold garbage values."""
    book = OrderBookModel()
    book.update_book(Message.add(1, Side.BUY, 100, 10))

    cancel_with_garbage = Message(msg_type=MsgType.CANCEL, order_id=1, side=Side.SELL, price=999, qty=0)
    event = book.update_book(cancel_with_garbage)

    expected = Event(event=EventType.CANCELED, order_id=1, side=Side.BUY, price=100, qty=10)
    assert event == expected


def test_reset_empties_book():
    """reset() removes every order."""
    book = OrderBookModel()
    book.update_book(Message.add(1, Side.BUY, 100, 10))

    book.reset()

    assert len(book) == 0


# ============================================================================
# Your turn: write these two tests, then delete the pytest.skip line.
# ============================================================================


def test_error_priority():
    """TODO: one message that triggers two errors at once. Assert the higher one wins.

    Cover at least:
      - BAD_QTY vs UNKNOWN_ID
      - DUP_ID vs BOOK_FULL
    """
    pytest.skip("TODO")


def test_id_reuse_after_removal():
    """TODO: after an order is CANCELED or FILLED, the same ID can be ADDed again.

    Also check the new order does not inherit the old order's side/price/remaining.
    """
    pytest.skip("TODO")


# ============================================================================
# Testbench input checks
# ============================================================================


def test_message_with_value_too_wide_raises_error():
    """A value that cannot fit in 16 bits is a testbench bug and must raise ValueError.

    `with pytest.raises(ValueError):` means: the code inside must raise
    ValueError, otherwise the test fails.
    """
    with pytest.raises(ValueError):
        Message.add(65536, Side.BUY, 100, 10)
