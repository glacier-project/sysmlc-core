import logging
import zipfile
from pathlib import Path

import pytest
import syside

from sysmlc.errors import FmuError
from sysmlc.semantics.fmi import (
    FmuPartNode,
    applied_fmu_metadata,
    fmu_import_definition,
    fmu_part_node,
    validate_fmu,
)
from sysmlc.sysml.loading import load_model

pytest.importorskip("fmpy")

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
FIX = MODELS_DIR / "showcase-frost" / "pendulum"


def _fmu_node(model: syside.Model) -> FmuPartNode:
    """The model's one FMU part node, via the extraction API alone."""
    fmu_import = fmu_import_definition(model)
    assert fmu_import is not None
    for usage in model.elements(
        syside.PartUsage,
        considered_document_kinds=syside.DocumentKind.MODEL,
    ):
        typings = usage.owned_typings.collect()
        definition = typings[0].type if typings else None
        if not isinstance(definition, syside.PartDefinition):
            continue
        applied = applied_fmu_metadata(definition, fmu_import)
        if applied is not None:
            return fmu_part_node(usage, definition, applied)
    raise AssertionError("model declares no FMU part")


# A synthetic FMI 3.0 model description matching the fmu01 declaration:
# outputs theta/d_theta, input u, all Float64. Only the description is
# needed for validation, so the archives hold no binaries.
_MATCHING = """<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="3.0" modelName="pendulum"
    instantiationToken="{11111111-2222-3333-4444-555555555555}">
  <CoSimulation modelIdentifier="pendulum"/>
  <ModelVariables>
    <Float64 name="time" valueReference="0" causality="independent"
        variability="continuous"/>
    <Float64 name="theta" valueReference="1" causality="output"
        variability="continuous" initial="calculated"/>
    <Float64 name="d_theta" valueReference="2" causality="output"
        variability="continuous" initial="calculated"/>
    <Float64 name="u" valueReference="3" causality="input"
        variability="continuous" start="0"/>
  </ModelVariables>
  <ModelStructure>
    <Output valueReference="1"/>
    <Output valueReference="2"/>
  </ModelStructure>
</fmiModelDescription>
"""


@pytest.fixture(scope="module")
def fmu_node() -> FmuPartNode:
    return _fmu_node(load_model(FIX))


def _archive(tmp_path: Path, description: str) -> Path:
    path = tmp_path / "test.fmu"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("modelDescription.xml", description)
    return path


def test_matching_declaration_passes(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    validate_fmu(fmu_node, path=_archive(tmp_path, _MATCHING))


def test_missing_archive_is_rejected(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    with pytest.raises(FmuError, match="does not exist"):
        validate_fmu(fmu_node, path=tmp_path / "absent.fmu")


def test_default_path_is_the_node_path(tmp_path: Path) -> None:
    # The staged model dir ships no archive, so the resolved default
    # path (beside the declaring file) must be reported as missing.
    node = _tuned_node(tmp_path)
    with pytest.raises(FmuError, match=r"x\.fmu"):
        validate_fmu(node)


# The FMI 2.0 description matching the fmu01 declaration: same names,
# 2.0's ScalarVariable/Real shape (SysML Real binds to FMI 2.0 `Real`).
_FMI2_MATCHING = """<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="2.0" modelName="pendulum"
    guid="{11111111-2222-3333-4444-555555555555}">
  <CoSimulation modelIdentifier="pendulum"/>
  <ModelVariables>
    <ScalarVariable name="theta" valueReference="1" causality="output"
        initial="calculated"><Real/></ScalarVariable>
    <ScalarVariable name="d_theta" valueReference="2" causality="output"
        initial="calculated"><Real/></ScalarVariable>
    <ScalarVariable name="u" valueReference="3" causality="input">
      <Real start="0"/>
    </ScalarVariable>
  </ModelVariables>
  <ModelStructure>
    <Outputs>
      <Unknown index="1"/>
      <Unknown index="2"/>
    </Outputs>
  </ModelStructure>
</fmiModelDescription>
"""


def test_fmi2_matching_declaration_passes(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    validated = validate_fmu(fmu_node, path=_archive(tmp_path, _FMI2_MATCHING))
    assert validated.fmi_version == "2"


def test_fmi3_version_is_recorded(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    validated = validate_fmu(fmu_node, path=_archive(tmp_path, _MATCHING))
    assert validated.fmi_version == "3"


def test_out_signal_binds_a_readable_local(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    # Exporters (Modelica tools, the Reference FMUs) publish states as
    # `local` instead of declared outputs; the getters read them all
    # the same, so an out-signal binding accepts them.
    description = _MATCHING.replace(
        'name="theta" valueReference="1" causality="output"',
        'name="theta" valueReference="1" causality="local"',
    )
    validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_out_signal_rejects_an_input_variable(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    description = _MATCHING.replace(
        'name="theta" valueReference="1" causality="output"',
        'name="theta" valueReference="1" causality="input"',
    )
    with pytest.raises(FmuError, match="readable `local`"):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_fmi2_model_exchange_only_is_rejected(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    description = _FMI2_MATCHING.replace(
        '<CoSimulation modelIdentifier="pendulum"/>',
        '<ModelExchange modelIdentifier="pendulum"/>',
    )
    with pytest.raises(FmuError, match="co-simulation"):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_model_exchange_only_is_rejected(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    description = _MATCHING.replace(
        '<CoSimulation modelIdentifier="pendulum"/>',
        '<ModelExchange modelIdentifier="pendulum"/>',
    )
    with pytest.raises(FmuError, match="co-simulation"):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_missing_variable_is_reported(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    description = _MATCHING.replace('name="d_theta"', 'name="renamed"')
    with pytest.raises(FmuError, match=r"'d_theta'.*not in the FMU"):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_wrong_causality_is_reported(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    description = _MATCHING.replace(
        'name="u" valueReference="3" causality="input"',
        'name="u" valueReference="3" causality="output"',
    )
    with pytest.raises(
        FmuError, match=r"'u' has causality 'output'.*in-signal binds"
    ):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_wrong_type_is_reported(fmu_node: FmuPartNode, tmp_path: Path) -> None:
    description = _MATCHING.replace('<Float64 name="u"', '<Int32 name="u"')
    with pytest.raises(FmuError, match="binds to 'Float64'"):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


def test_all_problems_reported_together(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    description = _MATCHING.replace('name="theta"', 'name="renamed"').replace(
        'name="u" valueReference="3" causality="input"',
        'name="u" valueReference="3" causality="local"',
    )
    with pytest.raises(FmuError) as excinfo:
        validate_fmu(fmu_node, path=_archive(tmp_path, description))
    message = str(excinfo.value)
    assert "'theta'" in message
    assert "'u'" in message


def test_unreadable_archive_is_rejected(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    path = tmp_path / "corrupt.fmu"
    path.write_bytes(b"not a zip")
    with pytest.raises(FmuError, match="cannot read"):
        validate_fmu(fmu_node, path=path)


def test_array_variable_is_rejected(
    fmu_node: FmuPartNode, tmp_path: Path
) -> None:
    # A scalar SysML declaration on an FMI 3.0 array would silently read
    # one element; reject instead (arrays have no binding surface).
    description = _MATCHING.replace(
        'name="u" valueReference="3" causality="input"\n'
        '        variability="continuous" start="0"/>',
        'name="u" valueReference="3" causality="input"\n'
        '        variability="continuous" start="0 0">'
        '<Dimension start="2"/></Float64>',
    )
    assert "Dimension" in description  # the replace matched
    with pytest.raises(FmuError, match=r"'u' is an array in the FMU"):
        validate_fmu(fmu_node, path=_archive(tmp_path, description))


# --- startup values (FMU parameters) and DefaultExperiment fallback ----

_TUNED_MODEL = """
package Tuned {
    private import ScalarValues::*;
    private import FmuBinding::*;

    item def Reading { attribute theta : Real; }
    port def P { out item reading : Reading; }

    part def Fmu {
        metadata FmuImport { path = "x.fmu"; %(metadata)s }
        attribute g : Real = -9.81;
        attribute strict : Boolean = true;
        port p : P;
    }
    part sys { part f : Fmu; }
}
"""

# Matches _TUNED_MODEL: output theta, parameter g (tunable), input-like
# Boolean strict, plus a DefaultExperiment carrying the preferred step.
_TUNED = """<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="3.0" modelName="tuned"
    instantiationToken="{11111111-2222-3333-4444-555555555555}">
  <CoSimulation modelIdentifier="tuned"/>
  <DefaultExperiment startTime="0.0" stopTime="10.0" stepSize="0.25"/>
  <ModelVariables>
    <Float64 name="time" valueReference="0" causality="independent"
        variability="continuous"/>
    <Float64 name="theta" valueReference="1" causality="output"
        variability="continuous" initial="calculated"/>
    <Float64 name="g" valueReference="2" causality="parameter"
        variability="tunable" start="-9.81"/>
    <Boolean name="strict" valueReference="3" causality="input"
        variability="discrete" start="true"/>
  </ModelVariables>
  <ModelStructure>
    <Output valueReference="1"/>
  </ModelStructure>
</fmiModelDescription>
"""


def _tuned_node(
    tmp_path: Path, metadata: str = "stepSize = 0.1;"
) -> FmuPartNode:
    from tests import _load_inline_model

    model = _load_inline_model(tmp_path, _TUNED_MODEL % {"metadata": metadata})
    return _fmu_node(model)


def test_matching_startup_values_pass(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path)
    validate_fmu(node, path=_archive(tmp_path, _TUNED))


def test_missing_startup_variable_is_reported(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path)
    description = _TUNED.replace('name="g"', 'name="gravity"')
    with pytest.raises(FmuError, match=r"'g' is not in the FMU"):
        validate_fmu(node, path=_archive(tmp_path, description))


def test_unsettable_causality_is_reported(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path)
    description = _TUNED.replace(
        'name="g" valueReference="2" causality="parameter"',
        'name="g" valueReference="2" causality="local"',
    )
    with pytest.raises(FmuError, match=r"'g' has causality 'local'"):
        validate_fmu(node, path=_archive(tmp_path, description))


def test_wrong_startup_type_is_reported(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path)
    description = _TUNED.replace('<Float64 name="g"', '<Int32 name="g"')
    with pytest.raises(FmuError, match=r"'g' is 'Int32'"):
        validate_fmu(node, path=_archive(tmp_path, description))


# The exact-initial idiom (VanDerPol's x0): the startup attribute names
# a variable that is ALSO an out-signal payload — legal because FMI lets
# initialization mode set any variable declared initial="exact".
_EXACT_MODEL = """
package Exact {
    private import ScalarValues::*;
    private import FmuBinding::*;

    item def Reading { attribute x0 : Real; }
    port def P { out item reading : Reading; }

    part def Fmu {
        metadata FmuImport { path = "x.fmu"; stepSize = 0.1; }
        attribute x0 : Real = 2.0;
        port p : P;
    }
    part sys { part f : Fmu; }
}
"""

_EXACT = """<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="3.0" modelName="exact"
    instantiationToken="{11111111-2222-3333-4444-555555555555}">
  <CoSimulation modelIdentifier="exact"/>
  <ModelVariables>
    <Float64 name="time" valueReference="0" causality="independent"
        variability="continuous"/>
    <Float64 name="x0" valueReference="1" causality="output"
        variability="continuous" initial="exact" start="2"/>
  </ModelVariables>
  <ModelStructure>
    <Output valueReference="1"/>
  </ModelStructure>
</fmiModelDescription>
"""


def test_exact_initial_output_startup_value_passes(tmp_path: Path) -> None:
    from tests import _load_inline_model

    model = _load_inline_model(tmp_path, _EXACT_MODEL)
    node = _fmu_node(model)
    validate_fmu(node, path=_archive(tmp_path, _EXACT))


def test_calculated_output_startup_value_is_rejected(tmp_path: Path) -> None:
    from tests import _load_inline_model

    model = _load_inline_model(tmp_path, _EXACT_MODEL)
    node = _fmu_node(model)
    description = _EXACT.replace(
        'initial="exact" start="2"', 'initial="calculated"'
    )
    with pytest.raises(
        FmuError, match=r"'x0' has causality 'output' \(initial 'calculated'\)"
    ):
        validate_fmu(node, path=_archive(tmp_path, description))


def test_fixed_parameter_does_not_warn(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Start values are applied inside initialization mode (the generated
    # startup re-runs it), so a `fixed` parameter is set where FMI
    # allows it and no longer draws a warning.
    monkeypatch.setattr(logging.getLogger("sysmlc"), "propagate", True)
    node = _tuned_node(tmp_path)
    description = _TUNED.replace(
        'name="g" valueReference="2" causality="parameter"\n        '
        'variability="tunable"',
        'name="g" valueReference="2" causality="parameter"\n        '
        'variability="fixed"',
    )
    with caplog.at_level("WARNING", logger="sysmlc.semantics.fmi"):
        validate_fmu(node, path=_archive(tmp_path, description))
    # No WARNING from the FMI validator (the substring "fixed" may appear
    # in unrelated INFO records, so assert on the records, not the text).
    fmi_warnings = [
        record
        for record in caplog.records
        if record.name == "sysmlc.semantics.fmi"
        and record.levelno >= logging.WARNING
    ]
    assert fmi_warnings == []


def test_step_size_falls_back_to_default_experiment(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path, metadata="")
    assert node.step_size is None
    resolved = validate_fmu(node, path=_archive(tmp_path, _TUNED))
    assert resolved.step_size == 0.25


def test_declared_step_size_wins_over_archive(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path)
    resolved = validate_fmu(node, path=_archive(tmp_path, _TUNED))
    assert resolved.step_size == 0.1


# --- tunable parameter bound by an in-signal ---------------------------

_TUNABLE_MODEL = """
package Tun {
    private import ScalarValues::*;
    private import FmuBinding::*;

    item def Gain { attribute g : Real; }
    item def Reading { attribute theta : Real; }
    port def P {
        in item gain : Gain;
        out item reading : Reading;
    }
    part def Fmu {
        metadata FmuImport { path = "x.fmu"; stepSize = 0.1; }
        port p : P;
    }
    part sys { part f : Fmu; }
}
"""

# Matches _TUNABLE_MODEL: g is a tunable parameter re-set by the in-signal.
_TUNABLE = """<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="3.0" modelName="tun"
    instantiationToken="{11111111-2222-3333-4444-555555555555}">
  <CoSimulation modelIdentifier="tun"/>
  <ModelVariables>
    <Float64 name="time" valueReference="0" causality="independent"
        variability="continuous"/>
    <Float64 name="theta" valueReference="1" causality="output"
        variability="continuous" initial="calculated"/>
    <Float64 name="g" valueReference="2" causality="parameter"
        variability="tunable" start="1.0"/>
  </ModelVariables>
  <ModelStructure>
    <Output valueReference="1"/>
  </ModelStructure>
</fmiModelDescription>
"""


def _tunable_node(tmp_path: Path) -> FmuPartNode:
    from tests import _load_inline_model

    model = _load_inline_model(tmp_path, _TUNABLE_MODEL)
    return _fmu_node(model)


def test_tunable_parameter_accepted_as_in_signal(tmp_path: Path) -> None:
    # FMI 3.0 lets a tunable parameter be re-set between communication
    # points, exactly what an in-signal does.
    node = _tunable_node(tmp_path)
    validate_fmu(node, path=_archive(tmp_path, _TUNABLE))


def test_fixed_parameter_rejected_as_in_signal(tmp_path: Path) -> None:
    # A non-tunable parameter cannot be re-set at each step.
    node = _tunable_node(tmp_path)
    description = _TUNABLE.replace(
        'variability="tunable"', 'variability="fixed"'
    )
    with pytest.raises(
        FmuError, match=r"'g' has causality 'parameter'.*tunable"
    ):
        validate_fmu(node, path=_archive(tmp_path, description))


# --- tolerance / startTime metadata resolution -------------------------


def test_tolerance_and_start_time_extracted(tmp_path: Path) -> None:
    node = _tuned_node(
        tmp_path, metadata="stepSize = 0.1; tolerance = 1e-6; startTime = 2.0;"
    )
    assert node.tolerance == 1e-6
    assert node.start_time == 2.0


# --- exposed parameters / variables ------------------------------------

_EXPOSED_MODEL = """
package Exp {
    private import ScalarValues::*;
    private import FmuBinding::*;

    item def Reading { attribute theta : Real; }
    port def P { out item reading : Reading; }

    part def Fmu {
        metadata FmuImport {
            path = "x.fmu"; stepSize = 0.1;
            %(exposed)s
        }
        port p : P;
    }
    part sys { part f : Fmu; }
}
"""

# theta output, gain tunable parameter, counter local Int32.
_EXPOSED = """<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="3.0" modelName="exp"
    instantiationToken="{11111111-2222-3333-4444-555555555555}">
  <CoSimulation modelIdentifier="exp"/>
  <ModelVariables>
    <Float64 name="time" valueReference="0" causality="independent"
        variability="continuous"/>
    <Float64 name="theta" valueReference="1" causality="output"
        variability="continuous" initial="calculated"/>
    <Float64 name="gain" valueReference="2" causality="parameter"
        variability="tunable" start="1.0"/>
    <Int32 name="counter" valueReference="3" causality="local"
        variability="discrete"/>
    <Float64 name="probe" valueReference="4" causality="output"
        variability="continuous" initial="calculated"/>
  </ModelVariables>
  <ModelStructure>
    <Output valueReference="1"/>
    <Output valueReference="4"/>
  </ModelStructure>
</fmiModelDescription>
"""


def _exposed_node(tmp_path: Path, exposed: str) -> FmuPartNode:
    from tests import _load_inline_model

    model = _load_inline_model(tmp_path, _EXPOSED_MODEL % {"exposed": exposed})
    return _fmu_node(model)


def test_exposed_resolved_with_types(tmp_path: Path) -> None:
    node = _exposed_node(
        tmp_path,
        'exposedParameters = ("gain"); exposedVariables = ("counter");',
    )
    resolved = validate_fmu(node, path=_archive(tmp_path, _EXPOSED))
    by_name = {e.name: e for e in resolved.exposed}
    assert by_name["gain"].sysml_type == "Real"
    assert by_name["gain"].settable is True
    assert by_name["counter"].sysml_type == "Integer"
    assert by_name["counter"].settable is False


def test_exposed_missing_variable_is_reported(tmp_path: Path) -> None:
    node = _exposed_node(tmp_path, 'exposedVariables = ("absent");')
    with pytest.raises(FmuError, match=r"exposed variable 'absent'.*not in"):
        validate_fmu(node, path=_archive(tmp_path, _EXPOSED))


def test_exposed_parameter_must_be_settable(tmp_path: Path) -> None:
    # 'probe' is an output (not port-addressed), not settable as a param.
    node = _exposed_node(tmp_path, 'exposedParameters = ("probe");')
    with pytest.raises(FmuError, match=r"exposed parameter 'probe'.*settable"):
        validate_fmu(node, path=_archive(tmp_path, _EXPOSED))


def test_no_step_size_anywhere_is_rejected(tmp_path: Path) -> None:
    node = _tuned_node(tmp_path, metadata="")
    description = _TUNED.replace(
        '  <DefaultExperiment startTime="0.0" stopTime="10.0" '
        'stepSize="0.25"/>\n',
        "",
    )
    with pytest.raises(FmuError, match="no DefaultExperiment stepSize"):
        validate_fmu(node, path=_archive(tmp_path, description))
