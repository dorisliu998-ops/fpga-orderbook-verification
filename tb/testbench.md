# Testbench Architecture

```
test --messages--> Driver --> DUT --> Output Monitor --actual--+
                               |                                v
                        Input Monitor --accepted--> Scoreboard (reference model inside)
```

The reference model is fed from the input monitor, not the driver, so it sees
exactly what the DUT accepted. Expected events wait in a list (oldest first);
each actual event is compared with the oldest one, because the spec requires
in-order output. Reset clears the model and the list.

## Conventions

- Drive inputs right after the rising edge; sample handshakes at the falling edge.
- Each run logs its random seed. Reproduce with `COCOTB_RANDOM_SEED=<seed>`.

## Components

| Module | Status | Description |
|---|---|---|
| `tb/transaction.py` | ✅ | `Message` and `Event` dataclasses; encoding enums |
| `tb/ref_model.py` | ✅ | Spec-level order book model |
| `tb/order_book_driver.py` | ✅ | Sends `Message`s with the ready/valid protocol; optional random idle cycles |
| `tb/order_book_input_monitor.py` | ✅ | Reports every accepted message (and every reset cycle) to the scoreboard |
| `tb/order_book_output_monitor.py` | ✅ | Records every delivered `Event`; reports it to the scoreboard |
| `tb/order_book_scoreboard.py` | ✅ | Feeds accepted messages to the model; checks actual events in order |
| `tb/order_book_testbench.py` | ✅ | Creates and connects all components; clock and reset |
| Coverage | ⏳ | |

### Transaction

`Message` and `Event` are immutable dataclasses. Static methods (`Message.add`, `Message.cancel`, `Message.execute`, `Event.reject`) set only the fields a type uses, by keyword.

Out-of-range field values raise `ValueError` at construction. These are testbench bugs and are distinct from DUT error cases such as `BAD_QTY`.

### Reference Model

`OrderBookModel.update_book(msg)` applies one accepted message to the book and returns the expected `Event`.

- Written from the spec only, independent of the RTL.
- Stores orders in a `dict` keyed by order ID. Table slot allocation is an RTL detail and is not modeled or compared.
- `_find_error(msg)` follows the spec priority: stateless field checks first, then table lookups.
- `reset()` clears the book. The scoreboard calls it when the input monitor observes reset.

Unit tests: `tests/test_ref_model.py` (no simulator required).
