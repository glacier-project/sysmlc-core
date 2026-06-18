import shutil
from pathlib import Path
from typing import Any

import pytest
import syside

from sysmlc.sysml.loading import load_model

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ice-lab"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip ``lf``-marked tests when ``lfc`` is not on PATH.

    The ``lf`` marker means "compile and run a generated Lingua Franca
    program", which needs ``lfc``. Enforcing the skip here (rather than per
    module) keeps the marker self-sufficient: any ``lf`` test is skipped when
    ``lfc`` is missing, so a new test cannot accidentally hard-fail CI by
    omitting its own guard.
    """
    if shutil.which("lfc") is not None:
        return
    skip_lf = pytest.mark.skip(reason="lfc is not on PATH")
    for item in items:
        if item.get_closest_marker("lf") is not None:
            item.add_marker(skip_lf)


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(MODEL_DIR)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param
