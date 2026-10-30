# Setup

## Requirements

| Tool | Version |
|---|---|
| Python | 3.12+ |
| Verilator | 5.036+ (minimum supported by cocotb 2.x) |
| cocotb | 2.x |

## macOS

```sh
xcode-select --install          # C++ compiler and make
brew install verilator python@3.12
verilator --version             # must be >= 5.036
```

## Linux (Ubuntu)

Distribution packages are usually older than 5.036. Build Verilator from source:
see the [Verilator install guide](https://verilator.org/guide/latest/install.html).

## Python Environment

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Tests

```sh
pytest -v                       # all tests
pytest -v tests/test_pipe_reg.py
```

Build output goes to `sim_build/`. Each run logs its random seed; rerun with the same seed via:

```sh
COCOTB_RANDOM_SEED=<seed> pytest -v tests/test_pipe_reg.py
```
