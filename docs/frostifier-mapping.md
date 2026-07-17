# frostifier mapping: SysML + FMI → Frost

The frostifier backend targets Lingua Franca programs running on the Frost
network layer. On this branch only the **FMI front end** is available: FMU
declaration in SysML, archive validation, and declaration scaffolding.
Program generation is reserved — `frostifier build` raises
`NotImplementedError`.

## Available

| Capability                             | Entry point                                                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Declare an FMU part in SysML           | `FmuBinding::FmuImport` metadata (bundled, `sysmlc/sysml/lib/fmu_binding.sysml`)                              |
| Behavior-parameter idiom               | `ModelBasedDesign` subset lib (`#fmu_behavior`/`#mbd_parameter`, `sysmlc/sysml/lib/model_based_design.sysml`) |
| Extract the declaration from a model   | `sysmlc.semantics.fmi.fmu_part_node` / `mbd_fmu_part_node`                                                    |
| Validate archive vs declaration        | `sysmlc.semantics.fmi.validate_fmu` (needs the `fmi` extra: fmpy)                                             |
| Scaffold a declaration from an archive | `sysmlc frostifier extract-fmu <archive.fmu> [-o file.sysml]`                                                 |
| Render item defs as Python dataclasses | `sysmlc.backends.frostifier.payloads.dataclass_lines`                                                         |

## 1. Declaring an FMU in SysML

A part def annotated with `FmuImport` is realized by the FMU archive at
`path`. Its typed ports declare the signal interface: an `out item` is a
signal the FMU emits at every communication point, an `in item` sets the
FMU's inputs. Payload attribute names bind to FMU variable names 1:1.

Part-def attributes with literal values are startup values, applied once in
the FMU's initialization mode (causality `parameter` or `input`).
`exposedParameters` / `exposedVariables` name FMU variables published
without a signal route: read-only probes and settable knobs.

Examples: `models/sm-examples/fmu01-pendulum`,
`models/sm-examples/fmu02-bouncing-ball`.

### Run vs experiment configuration

`stepSize` is the co-simulation communication interval; `stopTime` bounds
the run. Both fall back to the archive's `DefaultExperiment` when omitted —
`validate_fmu` returns the resolved declaration.

## 2. Validation

`validate_fmu` opens the archive with fmpy and checks the declaration
against `modelDescription.xml`: variable existence, type compatibility
(per-version type maps), causality, and scalar-only payloads. FMI 2.0 and
3.0 co-simulation are accepted; the FMI major version is recorded on the
extracted node.

## 3. Scaffolding: extract-fmu

`sysmlc frostifier extract-fmu` is the inverse of extraction: it reads
`modelDescription.xml` and writes a ready-to-edit `FmuImport` part def —
inputs and outputs grouped into one `in`/`out` item each, parameters with
start values as startup attributes, `DefaultExperiment` mapped to
`stepSize`/`stopTime`, and unbindable variables listed in a doc comment.
`FmuImport::path` is emitted relative to the output file.

## 4. Not yet available

Frost program generation: LF component assembly, `FrostChannel` routing
over the FrostLink, `frost_config.yml`, and the `src/`+`resources/` output
layout. The backend registers as reserved and rejects `build`/`run`.

## 5. Conformance

`tests/semantics/test_fmi.py` pins extraction and validation over the
`sysmlc.semantics.fmi` API.
