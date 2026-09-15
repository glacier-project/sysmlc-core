from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import sys
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import syside

from sysmlc.backends import Backend, OutputOptions, discover_backends
from sysmlc.errors import SysmlcError
from sysmlc.logging import configure_logging
from sysmlc.sysml.foreign_artifact.base import (
    ForeignArtifact,
    parse_raw_file,
    resolve_foreign_artifact,
)
from sysmlc.sysml.foreign_artifact.languages import SUPPORTED_LANG
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import (
    exhibited_state_defs,
    resolve,
    rig_definitions,
    state_definitions,
    top_level_part_usages,
)
from sysmlc.values import configure_model, load_values, select_values

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["main"]

logger = logging.getLogger("sysmlc.cli")
__version__ = version("sysmlc")


class CliError(SysmlcError):
    """A user-facing error, reported as a message without a traceback."""


def _resolve_foreign(
    backend: Backend,
    args: argparse.Namespace,
    model_dir: Path,
    model: syside.Model,
    element_qn: str,
) -> list[ForeignArtifact]:
    external: list[ForeignArtifact] = []
    supported = backend.supported_foreign_artifact_languages()
    for lang in SUPPORTED_LANG:
        if lang not in supported:
            continue
        paths: list[Path] | None = getattr(args, lang, None)
        for path in paths or ():
            external.append(parse_raw_file(path, lang))
        external.extend(
            resolve_foreign_artifact(
                model_dir,
                model,
                element_qn,
                lang,
            )
        )

    return external


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


def _load_external_modules(external: list[ForeignArtifact]) -> None:
    """Import every Python external artifact under its own module stem."""
    for artifact in external:
        if artifact.lang == "python":
            _load_external_module(artifact.path)


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
        _add_run_arguments(run, backend)
        run.set_defaults(_backend=backend)
    return parser


def _add_build_arguments(
    build: argparse.ArgumentParser, backend: Backend
) -> None:
    """Add the shared build inputs, plus ``-f`` when the backend has formats."""
    build.add_argument(
        "model",
        type=Path,
        help=(
            "path to a SysML model directory, or the name of a bundled "
            "corpus model (e.g. sm-examples/sm01-helloworld; requires "
            "the sysmlc-models package)"
        ),
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
    _add_foreign_arguments(build, backend)
    if backend.accepts_target_options():
        build.add_argument(
            "--timeout",
            help="run timeout for the generated program's target header, "
            'e.g. "5 sec" (top-level part usages only)',
        )
        build.add_argument(
            "--fast",
            action="store_true",
            help="enable fast mode in the generated program's target header "
            "(top-level part usages only)",
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


_FOREIGN_LANG_LABELS: dict[str, str] = {"c": "C", "c_h": "C header"}


def _add_foreign_arguments(
    parser: argparse.ArgumentParser, backend: Backend
) -> None:
    """Add one path option for each foreign language consumed by a backend."""
    for lang in SUPPORTED_LANG:
        if lang not in backend.supported_foreign_artifact_languages():
            continue
        label = _FOREIGN_LANG_LABELS.get(lang, lang.capitalize())
        parser.add_argument(
            f"--{lang}",
            type=Path,
            action="append",
            help=(
                f"a {label} file whose top-level functions back external "
                "calc-def calls, matched to SysML functions by simple "
                "name (a companion file that defines none, e.g. a header, "
                "is still carried along); repeat for more than one file"
            ),
        )


def _add_run_arguments(run: argparse.ArgumentParser, backend: Backend) -> None:
    """Add the inputs for a ``run`` command."""
    run.add_argument(
        "model",
        type=Path,
        help=(
            "path to a SysML model directory, or the name of a bundled "
            "corpus model (e.g. sm-examples/sm01-helloworld; requires "
            "the sysmlc-models package)"
        ),
    )
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
    _add_foreign_arguments(run, backend)


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
    args: argparse.Namespace,
) -> tuple[tuple[str, str], ...]:
    """Build the target-header options from ``--fast``/``--timeout``.

    Both flags exist only for backends that declare
    :meth:`Backend.accepts_target_options`, so absent flags yield no options.
    """
    options: list[tuple[str, str]] = []
    if getattr(args, "fast", False):
        options.append(("fast", "true"))
    timeout = getattr(args, "timeout", None)
    if timeout is not None:
        options.append(("timeout", timeout))
    return tuple(options)


def _resolve_model_dir(model: Path) -> Path:
    """Resolve the ``model`` argument to a model directory on disk.

    An existing directory is returned as-is. Otherwise the argument is
    treated as the name of a bundled corpus model (for example
    ``sm-examples/sm01-helloworld``) and resolved through the optional
    ``sysmlc-models`` package.

    Args:
        model: The raw ``model`` command-line argument.

    Returns:
        The directory holding the model's SysML sources.

    Raises:
        CliError: If the argument is neither an existing directory nor
            the name of a bundled corpus model.
    """
    if model.is_dir():
        return model
    try:
        from sysmlc_models.catalog import model_path
    except ImportError:
        raise CliError(
            f"model directory {str(model)!r} does not exist (install "
            "sysmlc-models to reference bundled corpus models by name)"
        ) from None
    try:
        return model_path(model.as_posix())
    except FileNotFoundError:
        raise CliError(
            f"{str(model)!r} is neither an existing directory nor the "
            "name of a bundled corpus model (such as "
            "'sm-examples/sm01-helloworld')"
        ) from None


def _cmd_build(args: argparse.Namespace) -> int:
    """Run a ``<backend> build`` command."""
    backend: Backend = args._backend
    model_dir = _resolve_model_dir(args.model)
    model = load_model(model_dir)
    if (
        getattr(args, "element", None) is None
        and "model" in backend.build_kinds()
    ):
        if getattr(args, "values", None) is not None:
            raise CliError(
                f"backend {backend.name!r} whole-model builds do not support "
                "--values yet"
            )
        artifact = backend.build_model(model)
        return _write_artifact(args, backend, "model", artifact, [])

    element_qn, kind = _select_element(model, args.element)
    target_options = _target_options(args)
    if target_options and kind != "part":
        raise CliError(
            "--timeout/--fast only apply to a top-level part usage "
            "(a generated main reactor); the selected element is a "
            f"{kind!r}"
        )

    if kind == "part":
        return _build_part(
            args, backend, model, model_dir, element_qn, target_options
        )

    is_rig = kind == "rig"
    if is_rig and "rig" not in backend.build_kinds():
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

    external: list[ForeignArtifact] = _resolve_foreign(
        backend, args, model_dir, model, element_qn
    )

    if is_rig:
        artifact = backend.build_composition(
            model, element_qn, external=external
        )
    else:
        artifact = backend.build(model, element_qn, external=external)
    return _write_artifact(args, backend, element_qn, artifact, external)


def _build_part(
    args: argparse.Namespace,
    backend: Backend,
    model: syside.Model,
    model_dir: Path,
    usage_qn: str,
    target_options: tuple[tuple[str, str], ...],
) -> int:
    """Build a top-level part usage into a main reactor and write it."""
    if "part" not in backend.build_kinds():
        raise CliError(f"backend {backend.name!r} cannot build a part system")
    if getattr(args, "values", None) is not None:
        raise CliError("--values is not supported with part systems yet")

    external: list[ForeignArtifact] = _resolve_foreign(
        backend, args, model_dir, model, usage_qn
    )

    artifact = backend.build_part(
        model, usage_qn, target_options=target_options, external=external
    )
    return _write_artifact(args, backend, usage_qn, artifact, external)


def _write_artifact(
    args: argparse.Namespace,
    backend: Backend,
    element_qn: str,
    artifact: object,
    external: list[ForeignArtifact],
) -> int:
    """Write the built artifact and report what was produced."""
    selected = getattr(args, "format", None)
    options = OutputOptions(
        output_dir=args.output,
        formats=(selected,) if selected else (),
        basename=element_qn.split("::")[-1],
    )
    written = backend.write(artifact, options)

    if not backend.owns_external_delivery():
        for fa in external:
            written.extend(_copy_external_support(fa.path, written))

    for path in written:
        logger.info("Wrote %s", path)
    logger.info("Built %s: %s", element_qn, backend.summary(artifact))
    return 0


def _copy_python_support(python_path: Path, written: list[Path]) -> list[Path]:
    """Copy a Python support module beside each generated artifact group.

    Kept as a compatibility wrapper for callers of the former helper.
    """
    return _copy_external_support(python_path, written)


def _copy_external_support(
    support_path: Path, written: list[Path]
) -> list[Path]:
    """Copy an external support file beside each generated artifact group.

    Backend artifacts may be flat or use one or more nested directories.
    A single copy per unique parent directory keeps imports relative to the
    generated files resolvable without duplicating work. Like every other
    build output, the copy overwrites a same-named file left by a previous
    build, so rebuilding into the same directory stays idempotent; only a
    collision with an artifact of the current build is refused.

    Args:
        support_path: User-supplied or textual-representation artifact.
        written: Paths returned by the backend's ``write`` operation.

    Returns:
        The newly copied paths.

    Raises:
        CliError: If the support filename collides with a different generated
            artifact.
    """
    source = support_path.resolve()
    artifact_paths = {path.resolve() for path in written}
    directories = sorted({path.parent.resolve() for path in written})
    copied: list[Path] = []
    for directory in directories:
        destination = directory / support_path.name
        resolved_destination = destination.resolve()
        if resolved_destination == source:
            continue
        if resolved_destination in artifact_paths:
            raise CliError(
                f"External support file {support_path.name!r} conflicts with "
                f"generated artifact {destination}"
            )
        shutil.copy2(support_path, destination)
        copied.append(destination)
    return copied


def _cmd_run(args: argparse.Namespace) -> int:
    """Run a ``<backend> run`` command: execute the model to quiescence."""
    backend: Backend = args._backend
    model_dir = _resolve_model_dir(args.model)
    model = load_model(model_dir)
    element_qn, kind = _select_element(model, args.element)
    if kind not in backend.run_kinds():
        raise CliError(f"backend {backend.name!r} cannot run a {kind!r}")

    external: list[ForeignArtifact] = _resolve_foreign(
        backend, args, model_dir, model, element_qn
    )

    load_external = None
    if external:
        if backend.defers_python_support_loading():
            load_external = partial(_load_external_modules, external)
        else:
            _load_external_modules(external)

    if kind == "statedef":
        run = backend.run_state_def
    else:
        run = backend.run_part_system
    if load_external is None:
        # The kwarg is omitted on the eager path so a backend released
        # before the load_external contract keeps running; only backends
        # that declare deferral (and thus implement the parameter) see it.
        report = run(
            model,
            element_qn,
            max_steps=args.max_steps,
            until=args.until,
            external=external,
        )
    else:
        report = run(
            model,
            element_qn,
            max_steps=args.max_steps,
            until=args.until,
            external=external,
            load_external=load_external,
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
    try:
        backends = discover_backends()
        args = _build_parser(backends).parse_args(argv)
        configure_logging("DEBUG" if args.verbose else "INFO")
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
