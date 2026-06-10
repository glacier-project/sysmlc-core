from __future__ import annotations

import argparse
import logging
import sys
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from sysmlc.backends import Backend, OutputOptions, discover_backends
from sysmlc.errors import SysmlcError
from sysmlc.logging import configure_logging
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import state_definitions

if TYPE_CHECKING:
    from collections.abc import Sequence

    import syside

__all__ = ["main"]

logger = logging.getLogger("sysmlc.cli")
__version__ = version("sysmlc")


class CliError(SysmlcError):
    """A user-facing error, reported as a message without a traceback."""


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
    return parser


def _add_build_arguments(
    build: argparse.ArgumentParser, backend: Backend
) -> None:
    """Add the shared build inputs, plus ``-f`` when the backend has formats."""
    build.add_argument(
        "model", type=Path, help="path to a SysML file or model directory"
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
        help="qualified name of the state definition to build",
    )
    formats = backend.formats()
    if formats:
        build.add_argument(
            "-f",
            "--format",
            choices=formats,
            help="output format (default: every supported format)",
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


def _cmd_build(args: argparse.Namespace) -> int:
    """Run a ``<backend> build`` command."""
    backend: Backend = args._backend
    model = load_model(args.model)
    element_qn = _select_state_def(model, args.element)

    artifact = backend.build(model, element_qn)
    selected = getattr(args, "format", None)
    options = OutputOptions(
        output_dir=args.output,
        formats=(selected,) if selected else (),
        basename=element_qn.split("::")[-1],
    )
    written = backend.write(artifact, options)

    for path in written:
        logger.info("Wrote %s", path)
    logger.info("Built %s: %s", element_qn, backend.summary(artifact))
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
        return _cmd_build(args)
    except (SysmlcError, ValueError) as error:
        logger.debug("command failed", exc_info=True)
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
