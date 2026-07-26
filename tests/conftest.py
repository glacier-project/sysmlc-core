import shutil
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


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip toolchain-gated tests when their tools are absent.

    The ``lf`` marker means "compile and run a generated Lingua Franca
    program" (needs ``lfc``). Enforcing the skip here (rather than per
    module) keeps the marker self-sufficient: a new test cannot
    accidentally hard-fail CI by omitting its own guard.
    """
    skip_lf = pytest.mark.skip(reason="lfc is not on PATH")
    for item in items:
        if (
            item.get_closest_marker("lf") is not None
            and shutil.which("lfc") is None
        ):
            item.add_marker(skip_lf)


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(MODEL_DIR)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param
