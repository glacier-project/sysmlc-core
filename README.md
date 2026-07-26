<p align="center">
  <img src="docs/assets/sysmlc-lockup-dark.svg" alt="SysMLC" width="400">
</p>

A compiler from SysML v2 models to executable simulations of industrial plants.

## Overview

`sysmlc` reads SysML v2 models (via [Syside](https://docs.sensmetry.com/automator/index.html))
and compiles their behavior to executable targets. This package is the core:
the SysML front-end, the shared state-machine semantics, the plugin contract,
and the `sysmlc` command-line interface.

The compilation targets live in separate backend packages. Each one registers
through the `sysmlc.backends` entry-point group, and the CLI discovers
whichever are installed:

| Back-end                                                             | Target                                                              | Status          |
| -------------------------------------------------------------------- | ------------------------------------------------------------------- | --------------- |
| [`quake`](https://github.com/glacier-project/sysmlc-quake)           | [sismic](https://github.com/AlexandreDecan/sismic) statecharts      | **in progress** |
| [`rosetta`](https://github.com/glacier-project/sysmlc-rosetta)       | [Lingua Franca](https://www.lf-lang.org/) reactors                  | **in progress** |
| [`statix`](https://github.com/glacier-project/sysmlc-statix)         | static-memory C for microcontrollers                                | **in progress** |
| [`frostifier`](https://github.com/glacier-project/sysmlc-frostifier) | [Frost](https://github.com/glacier-project/frost) plant simulations | planned         |

Each backend's repository documents its own construct-by-construct mapping,
usage, and examples.

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
uv pip install git+https://github.com/glacier-project/sysmlc-quake@dev
```

## Usage

The SysML model corpora live in the separate
[sysmlc-models](https://github.com/glacier-project/sysmlc-models) package,
installed automatically by `uv sync --extra dev` (standalone installs opt
in with the `models` extra: `sysmlc[models]`). Backend commands accept
either a path to a model directory or the name of a bundled corpus model
such as `sm-examples/sm01-helloworld`.

List the installed backends:

```bash
uv run sysmlc backends
```

Every installed backend exposes the same build command shape:

```bash
uv run sysmlc <backend> build sm-examples/sm01-helloworld \
  -e SM01::Machine -o out/
```

Attribute initial values can be overridden at build time from a hierarchical
YAML file when building a state definition (nesting mirrors qualified names;
works with any backend). Given a `values.yaml` like:

```yaml
SM01:
  Machine:
    speed: 2.5
```

```bash
uv run sysmlc <backend> build sm-examples/sm01-helloworld \
  -e SM01::Machine --values values.yaml -o out/
```

To explore a plant model's structure and OPC-UA metadata (the `ice-lab` model):

```bash
uv run python examples/load_model.py
```

## Development

```bash
uv run pre-commit install
uv run pre-commit run --all-files
uv run tox
```

Run the test suite, type checker, and linter directly:

```bash
uv run pytest
uv run pyrefly check
uv run ruff check
```

The core's test suite runs with no backend installed: the CLI tests exercise
the machinery through a fake backend registered by the tests themselves.
