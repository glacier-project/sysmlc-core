from __future__ import annotations

import argparse
import atexit
import importlib.util
import logging
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import syside

from sysmlc.backends import Backend, OutputOptions, discover_backends
from sysmlc.errors import SysmlcError
from sysmlc.logging import configure_logging
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import (
    exhibited_state_defs,
    resolve,
    rig_definitions,
    state_definitions,
    top_level_part_usages,
)
from sysmlc.sysml.textual_representation import (
    extract_textual,
    module_function_names,
    write_module,
)
from sysmlc.values import configure_model, load_values, select_values

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = ["main"]

logger = logging.getLogger("sysmlc.cli")
__version__ = version("sysmlc")


class CliError(SysmlcError):
    """A user-facing error, reported as a message without a traceback."""


_PYTHON_BACKENDS = frozenset({"rosetta", "quake"})


def _parse_external(python_path: Path) -> tuple[str, frozenset[str]]:
    """Parse a ``--python`` file into ``(module_stem, sync_function_names)``.

    Only top-level synchronous ``def``s are eligible; an ``async def`` cannot
    back a synchronous reaction call.

    Raises:
        CliError: If the file cannot be read or is not valid Python.
    """
    try:
        names = module_function_names(python_path)
    except OSError as error:
        raise CliError(
            f"cannot read --python file {python_path}: {error}"
        ) from error
    except SyntaxError as error:
        raise CliError(
            f"--python file {python_path} is not valid Python: {error}"
        ) from error
    return python_path.stem, names


def _parse_python_arg(
    args: argparse.Namespace, backend: Backend
) -> tuple[Path, tuple[str, frozenset[str]]] | tuple[None, None]:
    """Gate and parse a command's ``--python`` flag.

    Returns:
        The flag's path paired with its ``_parse_external`` result, or
        ``(None, None)`` when ``--python`` was not given.

    Raises:
        CliError: If the backend does not support ``--python``, or if the
            file cannot be read or is not valid Python.
    """
    python_path: Path | None = getattr(args, "python", None)
    if python_path is None:
        return None, None
    if backend.name not in _PYTHON_BACKENDS:
        raise CliError(f"backend {backend.name!r} does not support --python")
    return python_path, _parse_external(python_path)


def _materialize_reps(
    model: syside.Model, backend: Backend, element_qn: str
) -> Path | None:
    """Write the model's Python rep bodies to a generated module file.

    Returns:
        The generated module's path, in a fresh temporary directory that
        is removed at process exit; or None when the backend does not
        consume backing Python modules or the model carries no Python
        textual representations.

    Raises:
        UnsupportedConstructError: If the model's rep bodies are invalid;
            see :func:`sysmlc.sysml.textual_representation.extract_textual`.
    """
    if backend.name not in _PYTHON_BACKENDS:
        return None
    extracted = extract_textual(model, element_qn)
    if extracted is None:
        return None
    module_name, source_lines = extracted
    out_dir = Path(tempfile.mkdtemp(prefix="sysmlc-reps-"))
    atexit.register(shutil.rmtree, out_dir, ignore_errors=True)
    return write_module(source_lines, out_dir, module_name)


def _resolve_python(
    args: argparse.Namespace,
    backend: Backend,
    model: syside.Model,
    element_qn: str,
) -> tuple[Path, tuple[str, frozenset[str]]] | tuple[None, None]:
    """Resolve the backing Python module: ``--python`` flag or model reps.

    An explicit ``--python`` file wins. Otherwise the model's Python
    textual representations, if any, are written to a generated module
    file. Either way the file goes through :func:`_parse_external`.

    Returns:
        The module's path paired with its ``_parse_external`` result, or
        ``(None, None)`` when there is neither a flag nor a rep.

    Raises:
        CliError: If the backend does not support ``--python``, or the
            explicit file cannot be read or is not valid Python.
        UnsupportedConstructError: If the model's rep bodies are invalid.
    """
    python_path, external = _parse_python_arg(args, backend)
    if python_path is not None and external is not None:
        return python_path, external
    generated = _materialize_reps(model, backend, element_qn)
    if generated is None:
        return None, None
    return generated, _parse_external(generated)


def _load_external_module(python_path: Path) -> None:
    """Import a ``--python`` file under its stem so preamble imports resolve.

    Registers the module in ``sys.modules`` under the file's stem, overwriting
    any existing same-stem entry, so an emitted ``from <stem> import <name>``
    resolves when a statechart preamble runs.

    Raises:
        ValueError: If the path is not an importable Python module.
        CliError: If executing the module's top level raises.
    """
    stem = python_path.stem
    spec = importlib.util.spec_from_file_location(stem, python_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import external module from {python_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        # Mirror the import system: a failed import must not leave the
        # broken half-executed module importable.
        del sys.modules[stem]
        raise CliError(
            f"--python file {python_path} failed to execute: {error}"
        ) from error


def _build_parser(backends: dict[str, Backend]) -> argparse.ArgumentParser:
    """Build the parser, exposing one subcommand per discovered backend.

    Each backend becomes ``sysmlc <backend> build ...``; argparse then gives
    backend-specific ``--help`` and validates the backend name natively, so
    there is no ``--backend`` flag to select.
    """
    parser = argparse.ArgumentParser(
        prog="sysmlc",
        description="Transpile SysML v2 models into target artifacts.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging on stderr",
    )
    commands = parser.add_subparsers(
        dest="command", required=True, metavar="command"
    )

    commands.add_parser("backends", help="list the installed backends")
    for name in sorted(backends):
        backend = backends[name]
        backend_parser = commands.add_parser(
            backend.name, help=backend.description
        )
        actions = backend_parser.add_subparsers(
            dest="action", required=True, metavar="action"
        )
        build = actions.add_parser(
            "build",
            help=f"build a {backend.name} artifact from a SysML model",
        )
        _add_build_arguments(build, backend)
        build.set_defaults(_backend=backend)
        run = actions.add_parser(
            "run",
            help=f"execute a {backend.name} model to quiescence",
        )
        _add_run_arguments(run)
        run.set_defaults(_backend=backend)
    return parser


def _add_build_arguments(
    build: argparse.ArgumentParser, backend: Backend
) -> None:
    """Add the shared build inputs, plus ``-f`` when the backend has formats."""
    build.add_argument(
        "model", type=Path, help="path to a SysML model directory"
    )
    build.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="directory to write the generated artifact into",
    )
    build.add_argument(
        "-e",
        "--element",
        help="qualified name of the state definition or rig to build",
    )
    formats = backend.formats()
    if formats:
        build.add_argument(
            "-f",
            "--format",
            choices=formats,
            help="output format (default: every supported format)",
        )
    build.add_argument(
        "--values",
        type=Path,
        help=(
            "YAML file overriding attribute initial values; nesting "
            "mirrors qualified names (Pkg -> Def -> attribute: value)"
        ),
    )
    build.add_argument(
        "--python",
        type=Path,
        help="(rosetta/quake state definitions) a Python file whose "
        "top-level functions back external calc-def calls; matched to SysML "
        "functions by simple name",
    )
    build.add_argument(
        "--timeout",
        help="(rosetta part systems only) LF run timeout for the generated "
        'main reactor\'s target header, e.g. "5 sec"',
    )
    build.add_argument(
        "--fast",
        action="store_true",
        help="(rosetta part systems only) set `fast: true` in the generated "
        "main reactor's target header",
    )


def _select_state_def(model: syside.Model, requested: str | None) -> str:
    """Resolve the state definition to build.

    Args:
        model: The loaded SysML model.
        requested: The ``--element`` qualified name, or ``None``.

    Returns:
        The qualified name of the state definition to build.

    Raises:
        CliError: If the model has no state definition, the requested one is
            absent, or none was requested while the model declares several.
    """
    state_defs = sorted(
        str(state_def.qualified_name) for state_def in state_definitions(model)
    )
    if not state_defs:
        raise CliError("the model contains no state definition")
    if requested is None:
        if len(state_defs) > 1:
            available = ", ".join(state_defs)
            raise CliError(
                f"the model declares several state definitions ({available}); "
                "select one with --element"
            )
        return state_defs[0]
    if requested not in state_defs:
        raise CliError(f"state definition {requested!r} not found")
    return requested


def _add_run_arguments(run: argparse.ArgumentParser) -> None:
    """Add the inputs for a ``run`` command."""
    run.add_argument("model", type=Path, help="path to a SysML model directory")
    run.add_argument(
        "-e",
        "--element",
        help="qualified name of the state definition or part usage to run",
    )
    run.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="safety cap on total macro steps (default: %(default)s)",
    )
    run.add_argument(
        "--until",
        type=float,
        help="stop at this simulated time in seconds, keeping the trace up "
        "to it (default: run to quiescence)",
    )
    run.add_argument(
        "--python",
        type=Path,
        help="a Python file whose top-level functions back external calc-def "
        "calls; matched to SysML functions by simple name",
    )


def _select_element(
    model: syside.Model, requested: str | None
) -> tuple[str, str]:
    """Resolve the element to build: ``(qualified name, kind)``.

    ``kind`` is ``"part"`` (a top-level part usage -> main reactor),
    ``"rig"`` (a two-exhibit testbench composition), or ``"statedef"`` (a
    lone state definition). An explicit ``--element`` selects by name; with
    no ``--element`` a model's single part usage wins, then a single rig,
    then the single-state-def rule. Existing models declare no qualifying
    part usage, so their selection is unchanged.
    """
    parts = sorted(
        str(usage.qualified_name) for usage in top_level_part_usages(model)
    )
    rigs = sorted(str(rig.qualified_name) for rig in rig_definitions(model))
    if requested is not None:
        if requested in parts:
            return requested, "part"
        if requested in rigs:
            return requested, "rig"
        return _select_state_def(model, requested), "statedef"
    if len(parts) == 1:
        return parts[0], "part"
    if len(parts) > 1:
        available = ", ".join(parts)
        raise CliError(
            f"the model declares several top-level part usages ({available}); "
            "select one with --element"
        )
    if len(rigs) == 1:
        return rigs[0], "rig"
    if len(rigs) > 1:
        available = ", ".join(rigs)
        raise CliError(
            f"the model declares several rigs ({available}); "
            "select one with --element"
        )
    return _select_state_def(model, None), "statedef"


def _target_options(
    args: argparse.Namespace, backend: Backend
) -> tuple[tuple[str, str], ...]:
    """Build the LF target options from ``--fast``/``--timeout`` (rosetta)."""
    options: list[tuple[str, str]] = []
    if getattr(args, "fast", False):
        options.append(("fast", "true"))
    timeout = getattr(args, "timeout", None)
    if timeout is not None:
        options.append(("timeout", timeout))
    if options and backend.name != "rosetta":
        raise CliError(
            f"backend {backend.name!r} does not support --timeout/--fast"
        )
    return tuple(options)


def _cmd_build(args: argparse.Namespace) -> int:
    """Run a ``<backend> build`` command."""
    backend: Backend = args._backend
    model = load_model(args.model)
    build_model: Callable[[syside.Model], object] | None = getattr(
        backend, "build_model", None
    )
    if getattr(args, "element", None) is None and build_model is not None:
        if getattr(args, "values", None) is not None:
            raise CliError(
                f"backend {backend.name!r} whole-model builds do not support "
                "--values yet"
            )
        if getattr(args, "python", None) is not None:
            raise CliError(
                f"backend {backend.name!r} whole-model builds do not support "
                "--python"
            )
        target_options = _target_options(args, backend)
        if target_options:
            raise CliError(
                f"backend {backend.name!r} whole-model builds do not support "
                "--timeout/--fast"
            )
        artifact = build_model(model)
        return _write_artifact(args, backend, "model", artifact, None)

    element_qn, kind = _select_element(model, args.element)
    target_options = _target_options(args, backend)
    if target_options and kind != "part":
        raise CliError(
            "--timeout/--fast only apply to a top-level part usage "
            "(a generated main reactor); the selected element is a "
            f"{kind!r}"
        )

    if kind == "part":
        return _build_part(args, backend, model, element_qn, target_options)

    build_composition: Callable[[syside.Model, str], object] | None = getattr(
        backend, "build_composition", None
    )
    is_rig = kind == "rig"
    if is_rig and build_composition is None:
        raise CliError(
            f"backend {backend.name!r} cannot build a rig composition; "
            "select a state definition with --element if the model declares one"
        )

    values_path = getattr(args, "values", None)
    if values_path is not None:
        tree = load_values(values_path)
        targets = (
            [
                str(sd.qualified_name)
                for _, sd in exhibited_state_defs(
                    model,
                    resolve(model, syside.PartDefinition, element_qn),
                )
            ]
            if is_rig
            else [element_qn]
        )
        for target_qn in targets:
            overrides = select_values(tree, target_qn)
            model = configure_model(model, target_qn, overrides)

    python_path, external = _resolve_python(args, backend, model, element_qn)

    build_kwargs: dict[str, object] = (
        {"external": external} if external is not None else {}
    )
    if is_rig:
        assert build_composition is not None  # guarded above
        artifact = build_composition(model, element_qn, **build_kwargs)
    else:
        artifact = backend.build(model, element_qn, **build_kwargs)
    return _write_artifact(args, backend, element_qn, artifact, python_path)


def _build_part(
    args: argparse.Namespace,
    backend: Backend,
    model: syside.Model,
    usage_qn: str,
    target_options: tuple[tuple[str, str], ...],
) -> int:
    """Build a top-level part usage into a main reactor and write it."""
    build_part: Callable[..., object] | None = getattr(
        backend, "build_part", None
    )
    if build_part is None:
        raise CliError(f"backend {backend.name!r} cannot build a part system")
    if getattr(args, "values", None) is not None:
        raise CliError("--values is not supported with part systems yet")

    python_path, external = _resolve_python(args, backend, model, usage_qn)

    build_kwargs: dict[str, object] = (
        {"external": external} if external is not None else {}
    )
    artifact = build_part(
        model, usage_qn, target_options=target_options, **build_kwargs
    )
    return _write_artifact(args, backend, usage_qn, artifact, python_path)


def _write_artifact(
    args: argparse.Namespace,
    backend: Backend,
    element_qn: str,
    artifact: object,
    python_path: Path | None,
) -> int:
    """Write the built artifact and report what was produced."""
    selected = getattr(args, "format", None)
    options = OutputOptions(
        output_dir=args.output,
        formats=(selected,) if selected else (),
        basename=element_qn.split("::")[-1],
    )
    written = backend.write(artifact, options)

    if python_path is not None:
        # Place the backing Python module (user-supplied or rep-generated)
        # beside the generated artifact(s) so that imports emitted in the
        # artifact preamble can resolve.
        for path in written:
            shutil.copy(python_path, path.parent / python_path.name)

    for path in written:
        logger.info("Wrote %s", path)
    logger.info("Built %s: %s", element_qn, backend.summary(artifact))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run a ``<backend> run`` command: execute the model to quiescence."""
    backend: Backend = args._backend
    model = load_model(args.model)
    element_qn, kind = _select_element(model, args.element)
    hook_name = {
        "statedef": "run_state_def",
        "part": "run_part_system",
    }.get(kind)
    hook = getattr(backend, hook_name, None) if hook_name else None
    if hook is None:
        raise CliError(f"backend {backend.name!r} cannot run a {kind!r}")

    python_path, external = _resolve_python(args, backend, model, element_qn)
    if python_path is not None:
        _load_external_module(python_path)

    report = hook(
        model,
        element_qn,
        max_steps=args.max_steps,
        until=args.until,
        external=external,
    )
    print(f"Ran {element_qn}:")
    print(report.render())
    if report.hit_step_cap:
        print(
            f"error: exceeded the {args.max_steps}-step safety cap; "
            "raise --max-steps or bound the run with --until",
            file=sys.stderr,
        )
        return 1
    return 0


def _cmd_backends(backends: dict[str, Backend]) -> int:
    """Run the ``backends`` command: list what is installed."""
    if not backends:
        print("No backends are installed.")
        return 0
    print("Installed backends:")
    for name in sorted(backends):
        backend = backends[name]
        formats = ", ".join(backend.formats()) or "none"
        print(f"  {name} — {backend.description}")
        print(f"      formats: {formats}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``sysmlc`` command.

    Args:
        argv: Argument list to parse; defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code: ``0`` on success, ``1`` on a user-facing error.
    """
    backends = discover_backends()
    args = _build_parser(backends).parse_args(argv)
    configure_logging("DEBUG" if args.verbose else "INFO")
    try:
        if args.command == "backends":
            return _cmd_backends(backends)
        if args.action == "run":
            return _cmd_run(args)
        return _cmd_build(args)
    except (SysmlcError, ValueError) as error:
        logger.debug("command failed", exc_info=True)
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
