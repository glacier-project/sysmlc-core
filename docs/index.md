# sysmlc

`sysmlc` is a pluggable-backend compiler from SysML v2 models to simulation
and execution artifacts. A shared front-end parses models with the Syside
Automator and walks their behavior into paradigm-neutral facts; product-named
backends render those facts to their targets.

```{toctree}
:maxdepth: 2
:caption: Contents

api
foreign-artifacts
```

## Development

Install the documentation dependencies and run the live documentation server:

```bash
uv sync --extra dev --extra docs
uv run sphinx-autobuild docs docs/_build/html
```

Build the static site with:

```bash
uv run tox -e docs
```

## API reference

The API reference is generated directly from the core package. Keep module,
class, and function docstrings current and the published API documentation
will follow.
