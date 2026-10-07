<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sysmlc-lockup-dark.svg">
    <img src="docs/assets/sysmlc-lockup-light.svg" alt="SysMLC" width="400">
  </picture>
</p>

<p align="center">
  A pluggable-backend compiler from SysML v2 models to simulation and execution artifacts.
</p>

**Status:** in development.

## Overview

`sysmlc` reads SysML v2 models (via [Syside](https://docs.sensmetry.com/automator/index.html))
and compiles their behavior to executable targets. This package is the core:
the SysML front-end, the shared state-machine semantics, the plugin contract,
and the `sysmlc` command-line interface.

The compilation targets live in separate backend packages. Each one registers
through the `sysmlc.backends` entry-point group, and the CLI discovers
whichever are installed:

| Back-end                                                             | Target                                                              | Status            |
| -------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------- |
| [`quake`](https://github.com/glacier-project/sysmlc-quake)           | [sismic](https://github.com/AlexandreDecan/sismic) statecharts      | **in progress**   |
| [`rosetta`](https://github.com/glacier-project/sysmlc-rosetta)       | [Lingua Franca](https://www.lf-lang.org/) reactors                  | **in progress**   |
| [`statix`](https://github.com/glacier-project/sysmlc-statix)         | static-memory C for microcontrollers                                | **in progress**   |
| [`frostifier`](https://github.com/glacier-project/sysmlc-frostifier) | [Frost](https://github.com/glacier-project/frost) plant simulations | **reserved stub** |

Each backend's repository documents its own construct-by-construct mapping,
usage, and examples. The model corpora live in
[sysmlc-models](https://github.com/glacier-project/sysmlc-models).
[`sysmlc`](https://github.com/glacier-project/sysmlc) assembles every
repository into a single checkout; its `ARCHITECTURE.md` describes how the
pieces fit together.

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

Installing a backend package beside the core enables its subcommand, for
example:

```bash
uv pip install git+https://github.com/glacier-project/sysmlc-quake@main
```

## Usage

The SysML model corpora live in the separate
[sysmlc-models](https://github.com/glacier-project/sysmlc-models) package,
installed automatically by `uv sync --extra dev` (standalone installs opt
in with the `models` extra: `sysmlc[models]`). Every command that takes a
model accepts either a path to a model directory or the name of a bundled
corpus model such as `sm-examples/sm01-helloworld`.

List the installed backends:

```bash
uv run sysmlc backends
```

### `build` — compile a model to artifacts

Every installed backend exposes the same build command shape:

```bash
uv run sysmlc <backend> build sm-examples/sm01-helloworld \
  -e SM01::Machine -o out/
```

| Flag                  | Meaning                                                                      |
| --------------------- | ---------------------------------------------------------------------------- |
| `-e`, `--element`     | qualified name of the state definition or rig to build                       |
| `-o`, `--output`      | directory to write the generated artifact into (default `output`)            |
| `-f`, `--format`      | output format, when the backend supports more than one                       |
| `--values`            | YAML file overriding attribute initial values                                |
| `--python`            | Python file backing external `calc def` calls, for backends that consume one |
| `--timeout`, `--fast` | target-header options, for backends that accept them                         |

`--element` can be omitted when the model declares exactly one candidate;
otherwise the CLI lists the alternatives and asks you to choose.

A `--values` file nests to mirror qualified names:

```yaml
SM01:
  Machine:
    speed: 2.5
```

```bash
uv run sysmlc <backend> build sm-examples/sm01-helloworld \
  -e SM01::Machine --values values.yaml -o out/
```

### `run` — execute a model to quiescence

Backends that can execute what they build also expose `run`, which loads the
model, builds it in memory, and simulates it without writing artifacts:

```bash
uv run sysmlc <backend> run sm-examples/sm01-helloworld -e SM01::Machine
```

| Flag              | Meaning                                                            |
| ----------------- | ------------------------------------------------------------------ |
| `-e`, `--element` | qualified name of the state definition or part usage to run        |
| `--max-steps`     | safety cap on total macro steps (default `1000`)                   |
| `--until`         | stop at this simulated time in seconds, keeping the trace up to it |
| `--python`        | Python file backing external `calc def` calls                      |

`examples/load_model.py` is a loader-only smoke test over the bundled
`ice-lab` plant model.

## How a build works

The pipeline from a model directory to target artifacts is the same for every
backend; only the last step differs.

1. **Load** — `sysml.loading.load_model(model_dir)` collects the model's files
   recursively and loads them, logs warnings, and raises `ValueError` on
   diagnostic errors.
1. **Walk to neutral facts** — `semantics.statemachine.driver.StateMachineDriver`
   resolves and walks the SysML `state def` and pushes paradigm-neutral facts
   (`StateFact`, `TransitionFact`, `AttributeBinding`, `ConstraintFact`) into a
   backend `TargetBuilder`. The driver renders nothing and knows nothing about
   any target, so this front-end is shared by every backend.
1. **Render the target** — the backend's `TargetBuilder` buffers the facts and
   assembles its own artifact, extending the shared Python expression code
   generator to translate guards, attribute initializers, and action bodies.
1. **Execute or serialize** — the backend runs the artifact, writes it to
   disk, or both.

## Writing a backend

A backend is a package that depends on the core, subclasses
`sysmlc.backends.base.Backend`, and registers itself through the entry-point
group:

```toml
[project.entry-points."sysmlc.backends"]
mytarget = "sysmlc_mytarget.backend:MyTargetBackend"
```

`build` and `write` are the two abstract methods; `formats`, `run_state_def`,
`build_part`, `consumes_python_support` and the rest are optional hooks whose
presence the CLI detects to decide which flags and subcommands to expose.

Installing the package makes `sysmlc mytarget` available; uninstalling it
removes the subcommand. A plugin whose import fails is skipped with a logged
warning, so one broken backend cannot take down the CLI, and two plugins
claiming the same name are refused.

The core never depends on a backend, not even for tests.

## Layout

```
sysmlc/
├── backends/         # Backend ABC and OutputOptions
├── semantics/        # state-machine driver, neutral facts, part graph
├── sysml/            # model loading, queries, traversal
├── codegen/          # neutral Python expression code generator
├── cli.py            # backend discovery and the command line
├── errors.py
├── logging.py
└── values.py
```

Alongside the package: `examples/`, `tests/` mirroring the package layout, and
`docs/` (Sphinx, MyST + Furo).

## Development

```bash
uv run pre-commit install        # once after cloning
uv run tox                       # tests, type checking, formatting, coverage, docs
uv run pytest                    # tests only
uv run pyrefly check             # type checking
uv run tox run -e formatter      # ruff check --fix and ruff format
```

Individual tox environments: `-e type`, `-e formatter`, `-e coverage`,
`-e security`, `-e build`, `-e docs`.
