from typing import Any

import pytest
import syside
from sysmlc_models.catalog import model_path

from sysmlc.sysml.loading import load_model

MODEL_DIR = model_path("ice-lab")


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(MODEL_DIR)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param
