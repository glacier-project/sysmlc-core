import sys
from collections.abc import Iterator
from typing import Any

import pytest
import syside
from sysmlc_models.catalog import model_path

from sysmlc.sysml.loading import load_model

MODEL_DIR = model_path("ice-lab")


@pytest.fixture
def fresh_external_modules() -> Iterator[None]:
    """Isolate the ``--python`` module stems the external-backing tests use.

    Both the CLI tests (via ``_load_external_module``) and the runner tests
    (via a real import off ``sys.path``) register the same stems in
    ``sys.modules``; dropping the entries before and after each test keeps
    every test on its own import path regardless of execution order.
    """
    for stem in ("ramp", "bump"):
        sys.modules.pop(stem, None)
    yield
    for stem in ("ramp", "bump"):
        sys.modules.pop(stem, None)


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(MODEL_DIR)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param
