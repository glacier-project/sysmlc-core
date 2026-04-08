<p align="center">
  <img src="docs/assets/sysml-frozen.png" alt="SysML2Frost" width="400">
</p>

# SysML2Frost

From SysML v2 models to Frost simulations of industrial plants.

## Overview

SysML2Frost parses SysML v2 models describing industrial plants and generates
[Frost](https://github.com/glacier-project/frost) simulation code, including
Lingua Franca reactor files and YAML data models.

## Prerequisites

This project uses [Syside Automator](https://docs.sensmetry.com/automator/index.html) for SysML v2
parsing. A license key is required.

Create a `.env` file in the project root:

```
SYSIDE_LICENSE_KEY=your-key-here
```

## Installation

```bash
uv sync --extra dev
```

## Usage

```bash
uv run python examples/load_model.py
```

## Development

```bash
uv run pre-commit install
uv run tox
```
