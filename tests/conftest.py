from pathlib import Path
from typing import Any

import pytest
import syside

from sysmlc.explore import SysideModelQueries
from sysmlc.loader import load_syside_model

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ice-lab"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(MODEL_DIR)


@pytest.fixture
def model_queries(model: syside.Model) -> SysideModelQueries:
    return SysideModelQueries(model)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param
