from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sysmlc.backends.rosetta.builder import build_program
from sysmlc.sysml.loading import load_model
from sysmlc.values import (
    ValuesError,
    configure_model,
    load_values,
    select_values,
)

if TYPE_CHECKING:
    from pathlib import Path

    from sysmlc.backends.rosetta.program import LfProgram

# A self-contained configurable machine: scalar parameters, an initial
# value, a string, a boolean, a composite with type-level defaults, and a
# quantity. `PointFixed` binds its field with `=` (fixed by the language).
MODEL = """package VPkg {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::*;

    attribute def Point {
        attribute x : Real default 0.5;
        attribute y : Real default 1.0;
    }

    attribute def PointFixed {
        attribute x : Real = 0.5;
    }

    state def Machine {
        in attribute setpoint : Real default 21.0;
        attribute temperature : Real := 18.0;
        attribute label : String := "off";
        attribute armed : Boolean := false;
        attribute pt : Point;
        attribute fixed : PointFixed;
        attribute pickDuration : DurationValue default 2 [min];
        entry;
            then idle;
        state idle;
    }
}
"""

QN = "VPkg::Machine"


def _configured(tmp_path: Path, values: dict) -> LfProgram:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "machine.sysml").write_text(MODEL)
    model = load_model(model_dir)
    configured = configure_model(model, model_dir, QN, values)
    return build_program(configured, QN)


def _state_var(program: LfProgram, name: str) -> str:
    (init,) = [v.init for v in program.reactor.state_vars if v.name == name]
    return init


# -- load / select ---------------------------------------------------------


def test_load_values_reads_nested_mapping(tmp_path: Path) -> None:
    f = tmp_path / "values.yaml"
    f.write_text("Thermostat:\n  Thermostat:\n    setpoint: 23.0\n")
    assert load_values(f) == {"Thermostat": {"Thermostat": {"setpoint": 23.0}}}


def test_load_values_empty_file_is_empty_mapping(tmp_path: Path) -> None:
    f = tmp_path / "values.yaml"
    f.write_text("")
    assert load_values(f) == {}


def test_load_values_rejects_non_mapping(tmp_path: Path) -> None:
    f = tmp_path / "values.yaml"
    f.write_text("- a\n- b\n")
    with pytest.raises(ValuesError, match="mapping"):
        load_values(f)


def test_load_values_rejects_bad_yaml(tmp_path: Path) -> None:
    f = tmp_path / "values.yaml"
    f.write_text("a: [unclosed\n")
    with pytest.raises(ValuesError, match="cannot parse"):
        load_values(f)


def test_select_values_walks_qualified_name() -> None:
    tree = {"Pkg": {"Machine": {"setpoint": 23.0, "pt": {"x": 0.7}}}}
    assert select_values(tree, "Pkg::Machine") == {
        "setpoint": 23.0,
        "pt": {"x": 0.7},
    }


def test_select_values_missing_element_is_empty() -> None:
    tree = {"Pkg": {"Machine": {"setpoint": 23.0}}}
    assert select_values(tree, "Pkg::Other") == {}
    assert select_values(tree, "Other::Machine") == {}


def test_select_values_rejects_scalar_entry() -> None:
    tree = {"Pkg": {"Machine": 5}}
    with pytest.raises(ValuesError, match="map attribute names"):
        select_values(tree, "Pkg::Machine")


def test_select_values_rejects_non_scalar_leaf() -> None:
    tree = {"Pkg": {"Machine": {"setpoint": [1, 2]}}}
    with pytest.raises(ValuesError, match="scalar"):
        select_values(tree, "Pkg::Machine")


# -- configure_model: source edits + reload ---------------------------------


def test_parameter_default_is_overridden(tmp_path: Path) -> None:
    program = _configured(tmp_path, {"setpoint": 23.5})
    (setpoint,) = [
        p for p in program.reactor.parameters if p.name == "setpoint"
    ]
    assert setpoint.default == "23.5"


def test_initial_value_is_overridden(tmp_path: Path) -> None:
    program = _configured(tmp_path, {"temperature": 25.0})
    assert _state_var(program, "temperature") == "25.0"


def test_string_override_renders_double_quoted(tmp_path: Path) -> None:
    program = _configured(tmp_path, {"label": "on"})
    assert _state_var(program, "label") == '"on"'


def test_boolean_override_renders_sysml_then_python(tmp_path: Path) -> None:
    program = _configured(tmp_path, {"armed": True})
    assert _state_var(program, "armed") == "True"


def test_composite_override_redefines_per_usage(tmp_path: Path) -> None:
    # `pt : Point` declares nothing locally: the override must inject a
    # usage-local redefinition, never touch Point's own defaults.
    program = _configured(tmp_path, {"pt": {"x": 0.7}})
    assert _state_var(program, "pt") == "SimpleNamespace(x=0.7, y=1.0)"


def test_fixed_binding_cannot_be_overridden(tmp_path: Path) -> None:
    # PointFixed binds x with `=`: SysML forbids redefining a binding, and
    # the configured model fails to reload with the language's own error.
    with pytest.raises(ValuesError, match="not valid SysML"):
        _configured(tmp_path, {"fixed": {"x": 0.9}})


def test_quantity_number_keeps_model_unit(tmp_path: Path) -> None:
    # 5 means 5 [min]; quantities bind as SI floats.
    program = _configured(tmp_path, {"pickDuration": 5})
    assert _state_var(program, "pickDuration") == "300.0"


def test_quantity_sysml_string_is_inserted_verbatim(tmp_path: Path) -> None:
    program = _configured(tmp_path, {"pickDuration": "90 [s]"})
    assert _state_var(program, "pickDuration") == "90.0"


def test_quantity_unit_kind_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValuesError, match="unit kind"):
        _configured(tmp_path, {"pickDuration": "3 [m]"})


def test_unknown_attribute_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValuesError, match="does not match an attribute"):
        _configured(tmp_path, {"setpoit": 1.0})


def test_unknown_composite_field_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValuesError, match="does not match a field"):
        _configured(tmp_path, {"pt": {"z": 1.0}})


def test_scalar_for_composite_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValuesError, match="composite"):
        _configured(tmp_path, {"pt": 1.0})


def test_mapping_for_scalar_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValuesError, match="not a composite"):
        _configured(tmp_path, {"temperature": {"x": 1.0}})


def test_empty_values_return_original_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "machine.sysml").write_text(MODEL)
    model = load_model(model_dir)
    assert configure_model(model, model_dir, QN, {}) is model
