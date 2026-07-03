from pathlib import Path

import pytest
import syside

from sysmlc.sysml.loading import load_model

_MODELS = Path(__file__).resolve().parents[3] / "models" / "sm-examples"

# The sm-examples referenced across the statix backend tests, by folder stem.
_WANTED = {
    "sm01",
    "sm02",
    "sm03",
    "sm04",
    "sm05",
    "sm06",
    "sm07",
    "sm08",
    "sm09",
    "sm11",
}


@pytest.fixture(scope="session")
def sm_models() -> dict[str, syside.Model]:
    """Load each referenced sm-example once, keyed by folder stem (sm01…)."""
    out: dict[str, syside.Model] = {}
    for folder in sorted(_MODELS.glob("sm*-*")):
        stem = folder.name.split("-")[0]
        if stem in _WANTED:
            out[stem] = load_model(folder)
    return out
