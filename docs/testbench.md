# Testbench Architecture

```
Stimulus -> Driver -> DUT -> Output Monitor --+
               |                              |
          Input Monitor -> Reference Model -> Scoreboard
```

## Conventions

- Drive inputs right after the rising edge; sample handshakes at the falling edge.
- Each run logs its random seed. Reproduce with `COCOTB_RANDOM_SEED=<seed>`.

## Components

| Module | Status | Description |
|---|---|---|
| `tb/transaction.py` | ✅ | `Message` and `Event` dataclasses; encoding enums |
| `tb/ref_model.py` | ✅ | Spec-level order book model |
| Driver | ⏳ | |
| Input / Output monitors | ⏳ | |
| Scoreboard | ⏳ | |
| Coverage | ⏳ | |

### Transaction

`Message` and `Event` are immutable dataclasses. Constructors (`Message.add`, `Message.cancel`, `Message.execute`) set only the fields a type uses.

Out-of-range field values raise `ValueError` at construction. These are testbench bugs and are distinct from DUT error cases such as `BAD_QTY`.

### Reference Model

`OrderBookModel.process(msg)` applies one accepted message and returns the expected `Event`.

- Written from the spec only, independent of the RTL.
- Stores orders in a `dict` keyed by order ID. Table slot allocation is an RTL detail and is not modeled or compared.
- Error checks follow the spec priority: stateless field checks first, then table lookups.
- `reset()` clears the book. The scoreboard calls it when the input monitor observes reset.

Unit tests: `tests/test_ref_model.py` (no simulator required).
