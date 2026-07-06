import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import syside

from sysmlc.sysml.loading import load_model

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ice-lab"


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
    program" (needs ``lfc``); the ``statix`` marker means "compile and run a
    generated C statechart project" (needs a C compiler + CMake). Enforcing
    the skips here (rather than per module) keeps each marker self-sufficient:
    a new test cannot accidentally hard-fail CI by omitting its own guard.
    """
    have_cc = bool(
        shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    )
    have_cmake = shutil.which("cmake") is not None
    skip_lf = pytest.mark.skip(reason="lfc is not on PATH")
    skip_statix = pytest.mark.skip(reason="a C compiler + CMake are required")
    for item in items:
        if (
            item.get_closest_marker("lf") is not None
            and shutil.which("lfc") is None
        ):
            item.add_marker(skip_lf)
        if item.get_closest_marker("statix") is not None and not (
            have_cc and have_cmake
        ):
            item.add_marker(skip_statix)


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(MODEL_DIR)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param
