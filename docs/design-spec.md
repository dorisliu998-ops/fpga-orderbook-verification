# Design Spec (v1)

## Scope

The DUT receives market data messages (`ADD`, `CANCEL`, `EXECUTE`), maintains a bounded order table, and emits exactly one event per accepted message.

v1 uses a structured (field-based) input interface. A byte-stream parser is planned for v2.

Out of scope: price-level aggregation, best bid/ask computation, sequence-gap detection, order entry.

## Parameters

| Name | Value | Description |
|---|---|---|
| `MAX_ORDERS` | 64 | Order table capacity |
| `FIFO_DEPTH` | 16 | Input FIFO entries |
| `ID_W` | 16 | Order ID width |
| `PRICE_W` | 16 | Price width, unit = $0.01 |
| `QTY_W` | 16 | Quantity width |

## Interfaces

Clock: `clk`, rising edge. Reset: `rst_n`, synchronous, active-low.

### Input (ready/valid)

| Signal | Width | Description |
|---|---|---|
| `in_valid` | 1 | Message valid |
| `in_ready` | 1 | DUT can accept (deasserted when FIFO is full) |
| `in_msg_type` | 2 | `0`=ADD, `1`=CANCEL, `2`=EXECUTE, `3`=reserved |
| `in_order_id` | 16 | |
| `in_side` | 1 | `0`=BUY, `1`=SELL (ADD only) |
| `in_price` | 16 | ADD only |
| `in_qty` | 16 | ADD, EXECUTE |

Fields not used by a message type are don't-care.

### Output (ready/valid)

| Signal | Width | Description |
|---|---|---|
| `out_valid` | 1 | Event valid |
| `out_ready` | 1 | Downstream can accept |
| `out_event` | 3 | See event table |
| `out_order_id` | 16 | Order ID of the message |
| `out_side` | 1 | Side of the order |
| `out_price` | 16 | Price of the order |
| `out_qty` | 16 | Quantity delta (see below) |
| `out_err` | 3 | Error code, valid only for `REJECT` |

`out_side` and `out_price` always come from the order table (or from the message for `ADD`), so `CANCEL` and `EXECUTE` events carry the stored values.

`out_qty` is the quantity change applied to the order's price level. A downstream consumer can therefore maintain per-level totals with a single add or subtract per event.

## Event Semantics

| Message | Condition | `out_event` | `out_qty` | Book effect |
|---|---|---|---|---|
| ADD | valid | `ADDED` (0) | `qty` | Insert order |
| CANCEL | valid | `CANCELED` (1) | remaining qty | Remove order |
| EXECUTE | `qty < remaining` | `EXECUTED` (2) | `qty` | `remaining -= qty` |
| EXECUTE | `qty == remaining` | `FILLED` (3) | `qty` | Remove order |
| any | error | `REJECT` (4) | 0 | **None** |

For `REJECT`, `out_order_id` echoes the input ID, and `out_side` and `out_price` are 0.

## Error Codes

| Code | Name | Condition |
|---|---|---|
| 0 | `NONE` | — |
| 1 | `BAD_TYPE` | `msg_type == 3` |
| 2 | `BAD_QTY` | ADD or EXECUTE with `qty == 0` |
| 3 | `BAD_PRICE` | ADD with `price == 0` |
| 4 | `DUP_ID` | ADD with an ID already active |
| 5 | `UNKNOWN_ID` | CANCEL or EXECUTE with an ID not active |
| 6 | `BOOK_FULL` | ADD while `MAX_ORDERS` orders are active |
| 7 | `QTY_UNDERFLOW` | EXECUTE with `qty > remaining` |

### Priority

If several conditions hold, the highest-priority code is reported:

```
BAD_TYPE > BAD_QTY > BAD_PRICE > DUP_ID / UNKNOWN_ID > BOOK_FULL > QTY_UNDERFLOW
```

Stateless field checks come before stateful table checks. This matches a decode stage followed by a lookup stage.

`QTY_UNDERFLOW` indicates that the local book has diverged from the exchange. The message is rejected without modifying the book, so the inconsistency is reported rather than masked.

## Invariants

1. **One-to-one:** every accepted input message produces exactly one output event.
2. **In-order:** events are emitted in the same order that messages were accepted.
3. **Reject is side-effect-free:** a `REJECT` never modifies the book.
4. **ID reuse:** after an order is removed (CANCEL or FILLED), its ID may be used by a new ADD.
5. **Capacity:** the number of active orders never exceeds `MAX_ORDERS`.

## Handshake Rules

- A transfer occurs on a rising edge where `valid && ready` is true.
- Once `valid` is asserted, it and the payload must stay stable until the transfer occurs.
- `in_ready` is low when the FIFO is full. No message is accepted, dropped, or duplicated while it is low.
- No fixed latency is specified in v1. Only ordering is checked.

## Reset

- On a rising edge with `rst_n == 0`, the order table and FIFO are cleared.
- `in_ready` and `out_valid` are 0 while `rst_n == 0`.
- A handshake on an edge where `rst_n == 0` does **not** count as a transfer.
- Messages in flight at reset are discarded and produce no event.
