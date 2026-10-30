# Low-Latency FPGA Market Data Feed Handler

A SystemVerilog market data processing pipeline with a Python/Cocotb verification environment, simulated on Verilator.

The DUT receives exchange-style messages (`ADD`, `CANCEL`, `EXECUTE`), maintains a bounded order table, and emits one book-update event per message.

This is a learning project. It does not connect to any exchange or place any orders.

## Architecture

```
Messages -> Input FIFO -> Parser -> Order Book Engine -> Event Output
```

## Stack

SystemVerilog · Python 3.12+ · Cocotb 2.x · Verilator · pytest · GitHub Actions

## Quick Start

```sh
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

Requires Verilator 5.036+. See [Setup](docs/setup.md).

## Layout

```
rtl/     SystemVerilog sources
           order_book_top.sv  DUT top: FIFO + order table + output register
           msg_fifo.sv        input message FIFO
           pipe_reg.sv        M1 toolchain bring-up example
tb/      Reusable verification components (Python)
tests/   cocotb testbenches and pytest unit tests
docs/    Spec, setup and testbench notes
```

## Docs

- [Setup](docs/setup.md)
- [Design Spec](docs/design-spec.md)
- [Testbench Architecture](docs/testbench.md)

## Roadmap

- [x] M0 Design spec
- [x] M1 Environment setup (Verilator + Cocotb)
- [x] M2 Transaction, reference model, pytest unit tests
- [x] M3 RTL v1 (structured interface)
- [ ] M4 Driver, monitors, scoreboard, directed tests
- [ ] M5 Constrained random and functional coverage
- [ ] M6 Backpressure, burst traffic, reset during traffic
- [ ] M7 Byte-stream parser (v2)
- [ ] M8 GitHub Actions regression
