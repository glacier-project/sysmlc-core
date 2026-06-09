from pathlib import Path

import syside

from sysmlc.loader import load_syside_model


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
