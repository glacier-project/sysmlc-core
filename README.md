<p align="center">
  <img src="docs/assets/sysmlc-lockup-dark.svg" alt="SysMLC" width="400">
</p>

A compiler from SysML v2 models to executable simulations of industrial plants.

## Overview

`sysmlc` reads SysML v2 models (via [Syside](https://docs.sensmetry.com/automator/index.html))
and compiles their behavior to executable targets.

Currently, it generates **[sismic](https://github.com/AlexandreDecan/sismic) statecharts**
from SysML state machines ready to execute and simulate.

One shared front-end feeds a family of product-named back-ends, one per target:

| Back-end     | Target                                                              | Status          |
| ------------ | ------------------------------------------------------------------- | --------------- |
| `quake`      | sismic statecharts                                                  | **in progress** |
| `rosetta`    | [Lingua Franca](https://www.lf-lang.org/) reactors                  | **in progress** |
| `frostifier` | [Frost](https://github.com/glacier-project/frost) plant simulations | planned         |
| `statix`     | static-memory C for microcontrollers                                | **in progress** |

## Prerequisites

This project uses [Syside Automator](https://docs.sensmetry.com/automator/index.html)
for SysML v2 parsing. A license key is required.

Create a `.env` file in the project root:

```
SYSIDE_LICENSE_KEY=your-key-here
```

## Installation

```bash
uv sync --extra dev
```

## Usage

Build and run a sismic statechart from one of the example state machines under
`models/sm-examples/` (accepts `01`, `sm01`, or the full folder name):

```bash
uv run python examples/run_sismic.py sm01
```

Or use the API directly:

```python
from sysmlc.loader import load_syside_model
from sysmlc.backends.quake import build_statechart

model = load_syside_model("models/sm-examples/sm01-helloworld")
statechart = build_statechart(model, "SM01::Machine")
```

The `sysmlc` CLI exposes one build command per backend:

```bash
sysmlc quake build models/sm-examples/sm01-helloworld \
  -e SM01::Machine -o out/
```

The **quake** backend can also execute a model with `run`, printing the
macro-step trace and each machine's final configuration. A lone state
definition runs as a single statechart; a top-level part usage runs one
interpreter per part on a shared clock:

```bash
sysmlc quake run models/sm-examples/part01-two-parts
```

Translate a state machine to a Lingua Franca modal-reactor program with the
**rosetta** backend. The showcase corpus under `models/showcase/` exercises
the supported construct set (enums, parameters, payloads, function calls,
hierarchy, parallel regions, and asserted constraints — the full
construct-by-construct mapping is documented in `docs/rosetta-mapping.md`,
including the showcase case studies):

```bash
sysmlc rosetta build models/showcase/milling-workcell \
  -e MillingWorkcell::millingWorkcellSystem -o out/
```

When a model has exactly one top-level part usage, `--element` can be omitted
and the CLI auto-selects the system target:

```bash
sysmlc rosetta build models/showcase/milling-workcell -o out/
```

To build only a bare state machine, select the state definition directly:

```bash
sysmlc rosetta build models/showcase/milling-workcell \
  -e MillingWorkcell::MillingWorkcellBehavior -o out/
```

Attribute initial values can be overridden at build time from a hierarchical
YAML file when building a state definition (nesting mirrors qualified names;
works with any backend):

```bash
sysmlc rosetta build models/showcase/thermostat \
  -e Thermostat::ThermostatBehavior \
  --values models/showcase/thermostat/values.yaml -o out/
```

Compile a flat SysML state machine to a self-contained, static-memory C project
with the **statix** backend (generated tables + guards/actions/context + a
bundled Power-of-10 runtime kernel).
The supported flat subset is the `sm01`–`sm07` examples; the full
construct-by-construct mapping and rejection list is in `docs/statix-mapping.md`:

```bash
sysmlc statix build models/sm-examples/sm01-helloworld -e SM01::Machine -o out/
# out/ is a self-contained C project:
cmake -S out -B out/build && cmake --build out/build
```

To explore a plant model's structure and OPC-UA metadata (the `ice-lab` model):

```bash
uv run python examples/load_model.py
```

## Development

```bash
uv run pre-commit install
uv run tox
```

Run the test suite, type checker, and linter directly:

```bash
uv run pytest
uv run mypy sysmlc
uv run ruff check
```

## Testing

The default test loop is fast and excludes the Lingua Franca compile tests:

```
.venv/bin/python -m pytest -m "not lf"   # or: tox
```

The `lf`-marked tests compile and run generated LF programs with `lfc`
(seconds per test). They live in `tests/backends/rosetta/lf/` (plus a few
inline-marked cases) and need `lfc` + Java on PATH:

```
.venv/bin/python -m pytest -m lf         # or: tox -e lf
```

When `lfc` is not on PATH, the `lf` tests are skipped automatically. CI runs
them in a dedicated `lf-test` job.
