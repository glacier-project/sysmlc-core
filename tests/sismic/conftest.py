from pathlib import Path

import pytest
import syside

from sysml2frost.loader import load_syside_model

SM01_MODEL_DIR = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "sm-examples"
    / "sm01-helloworld"
)


@pytest.fixture(scope="module")
def sm01_model() -> syside.Model:
    return load_syside_model(SM01_MODEL_DIR)
