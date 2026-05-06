from pathlib import Path

import pytest
import syside

from sysml2frost.loader import load_syside_model


def test_load_syside_model_loads_ice_lab(model: syside.Model) -> None:
    assert isinstance(model, syside.Model)
    assert model.documents


def test_load_syside_model_raises_on_diagnostic_errors(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken.sysml"
    broken.write_text("part def { this is not valid syntax")

    with pytest.raises(ValueError, match="syside diagnostics"):
        load_syside_model(tmp_path)
