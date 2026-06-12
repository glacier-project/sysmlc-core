# SysMLC

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
from sysmlc.generator.sismic import build_statechart

model = load_syside_model("models/sm-examples/sm01-helloworld")
statechart = build_statechart(model, "SM01::Machine")
```

A unified `sysmlc` CLI is planned to build for any back-end:

```bash
# planned
sysmlc build models/sm-examples/sm01-helloworld --backend quake
```

Translate a state machine to a Lingua Franca modal-reactor program with the
**rosetta** backend. The showcase corpus under `models/showcase/` exercises
the supported construct set (enums, parameters, payloads, function calls,
hierarchy, parallel regions, and asserted constraints — the full
construct-by-construct mapping is documented in `docs/rosetta-mapping.md`,
and `docs/showcase-corpus.md` describes the corpus, including the two
flagship case studies, milling-workcell and batch-reactor):

```bash
sysmlc rosetta build models/showcase/milling-workcell \
  -e MillingWorkcell::MillingWorkcell -o out/
```

Attribute initial values can be overridden at build time from a
hierarchical YAML file (nesting mirrors qualified names; works with any
backend):

```bash
sysmlc rosetta build models/showcase/thermostat -e Thermostat::Thermostat \
  --values models/showcase/thermostat/values.yaml -o out/
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
