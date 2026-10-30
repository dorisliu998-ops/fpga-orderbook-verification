"""Scoreboard for the order book DUT.

What a scoreboard does:
  Decides pass/fail by comparing what the DUT did with what it should have
  done. It never touches DUT signals; it only receives transactions from
  the monitors.

How this one works:
  - The input monitor calls on_message_accepted(message) for every message
    the DUT accepted. The scoreboard gives it to the reference model, which
    updates its own book and returns the expected Event. That expected event
    is added to the end of a waiting list.
  - The output monitor calls on_output_event(actual_event) for every event
    the DUT delivered. The scoreboard takes the oldest expected event off the
    front of the waiting list and compares. (The spec says events come out in
    the same order as messages went in, so oldest-first is the right match.)
  - The input monitor calls on_reset() while the DUT is in reset. The spec
    says reset empties the book and drops messages in flight, so the model
    is reset and the waiting list is emptied.
  - At the end of a test, check_end_of_test() fails the test if any event
    did not match, or if any expected event never came out.
"""

from tb.ref_model import OrderBookModel


class OrderBookScoreboard:
    """Predicts expected events with the reference model and checks actual events against them."""

    def __init__(self, log):
        """log: a logger for messages, normally dut._log."""
        self.log = log
        self.model = OrderBookModel()
        self.waiting_expected = []  # list of (message, expected_event), oldest first
        self.mismatches = []  # list of text descriptions of every failure
        self.checked_count = 0  # number of events compared so far

    def on_message_accepted(self, message):
        """Called by the input monitor: the DUT accepted this message."""
        expected_event = self.model.update_book(message)
        self.waiting_expected.append((message, expected_event))

    def on_output_event(self, actual_event):
        """Called by the output monitor: the DUT delivered this event."""
        if len(self.waiting_expected) == 0:
            description = f"unexpected extra event from DUT: {actual_event}"
            self.mismatches.append(description)
            self.log.error(description)
            return

        message, expected_event = self.waiting_expected.pop(0)  # oldest first
        self.checked_count += 1
        if actual_event != expected_event:
            description = (
                f"mismatch for message {message}\n"
                f"    expected {expected_event}\n"
                f"    got      {actual_event}"
            )
            self.mismatches.append(description)
            self.log.error(description)

    def on_reset(self):
        """Called by the input monitor while the DUT is in reset."""
        self.model.reset()
        self.waiting_expected = []

    def pending_count(self):
        """Number of expected events still waiting for the DUT to output them."""
        return len(self.waiting_expected)

    def check_end_of_test(self):
        """Fail the test if anything went wrong. Call once, after traffic has drained."""
        self.log.info("scoreboard: %d events checked, %d mismatches", self.checked_count, len(self.mismatches))
        assert len(self.mismatches) == 0, f"{len(self.mismatches)} mismatches, first one: {self.mismatches[0]}"
        assert self.pending_count() == 0, (
            f"{self.pending_count()} expected events never came out, "
            f"first one: {self.waiting_expected[0][1]} (for message {self.waiting_expected[0][0]})"
        )
