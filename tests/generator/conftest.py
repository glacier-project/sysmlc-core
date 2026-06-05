import pytest
from pathlib import Path
import syside

from sysml2frost.loader.syside_loader import load_syside_model

@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> str:
    return request.param

def _load_inline_model(tmp_path: Path, source: str) -> syside.Model:
    model_path = tmp_path / "model.sysml"
    model_path.write_text(source)
    return load_syside_model(tmp_path)

def _single_element[T: syside.Element](
    model: syside.Model,
    kind: type[T],
) -> T:
    elements = list(model.elements(kind, include_subtypes=True))
    assert len(elements) == 1
    return elements[0]