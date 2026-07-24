#!/usr/bin/env python3
"""Build and run every showcase and sm-examples model through quake.

Sweeps the two corpora (``models/showcase/`` and ``models/sm-examples/``)
through the CLI and reports a per-target verdict. Unlike rosetta's
``models/showcase/run_all.py`` pipeline, quake's two verbs are
independent checks: ``build`` writes the YAML and PlantUML artifacts,
while ``run`` re-loads the model and executes it in-process, never
reading the build's output.

Pipeline (per model folder):

1. **Targets** - the folder is loaded once to enumerate what to sweep:
   every top-level part usage if the model declares any (each composes
   its parts' exhibited machines), otherwise every state definition.
2. **Build** - ``python -m sysmlc.cli quake build <model-dir> -e <qn>
   -o examples/build/<corpus>/<model>/<qn>`` exercises artifact
   emission (``build/`` is gitignored).
3. **Run** - ``python -m sysmlc.cli quake run <model-dir> -e <qn>
   --until <T> --max-steps <N>`` executes to the time bound.

A folder that ships exactly one ``*.py`` file has it forwarded as
``--python`` to both verbs (external calc-def backing). Both stages
always run: a build failure never hides the run verdict. Targets listed
in ``EXPECTED_FAILURES`` (rejection fixtures and known gaps) must fail
at each recorded stage; the sweep stays green there and prints the
reason, while a recorded stage that passes turns the sweep red so the
table cannot go stale.

Usage:
    python examples/run_all_quake.py [--only thermostat sm03-guard]
        [--until 2.0] [--max-steps 5000]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sysmlc_models.catalog import model_path

from sysmlc import configure_logging
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import state_definitions, top_level_part_usages

EXAMPLES_DIR = Path(__file__).resolve().parent
MODELS_DIR = EXAMPLES_DIR.parent / "models"
CORPUS_DIRS = (MODELS_DIR / "showcase", model_path("sm-examples"))
BUILD_ROOT = EXAMPLES_DIR / "build"


@dataclass(frozen=True)
class ExpectedFailure:
    """A target that must fail, and at which stages.

    Attributes:
        stages: The stages whose failure is expected: ``("build",
            "run")`` for a model both verbs must reject, ``("run",)``
            when only execution fails.
        reason: Why failing is correct behavior, shown in the report.
    """

    stages: tuple[str, ...]
    reason: str


# Keyed by target label: <corpus>/<model folder>::<element leaf name>.
EXPECTED_FAILURES: dict[str, ExpectedFailure] = {
    "showcase/furuta-pendulum::furutaSystem": ExpectedFailure(
        stages=("run",),
        reason=(
            "the physics module imports a generated types module that "
            "quake does not emit, and the shared model is deliberately "
            "nondeterministic; the deterministic variant lives in "
            "sm-examples/furuta-pendulum"
        ),
    ),
    "sm-examples/part-zero-exhibit::sys": ExpectedFailure(
        stages=("build", "run"),
        reason="rejection fixture: the part declares no exhibited state",
    ),
    "sm-examples/part-multi-exhibit::sys": ExpectedFailure(
        stages=("build", "run"),
        reason="rejection fixture: a part exhibits more than one state",
    ),
    "sm-examples/part-undeclared-via::sys": ExpectedFailure(
        stages=("build", "run"),
        reason=(
            "rejection fixture: a send routes via a port its part does "
            "not declare"
        ),
    ),
}


@dataclass
class Result:
    """Outcome of one target's build/run sweep.

    Attributes:
        label: ``<corpus>/<model>::<element leaf name>``.
        stage: The check the verdict is for: ``load``, ``build``, or
            ``run``.
        ok: Sweep verdict; an expected failure at a recorded stage
            counts as ok.
        detail: The stage's closing summary line on success, the CLI's
            error line or the expected-failure reason otherwise.
    """

    label: str
    stage: str
    ok: bool
    detail: str = ""


def _model_dirs(only: list[str] | None) -> list[Path]:
    """Return the model folders to sweep, sorted per corpus.

    Args:
        only: Folder names (``thermostat``) or corpus-qualified names
            (``showcase/furuta-pendulum``) to restrict the sweep to.

    Returns:
        Model directories containing at least one ``*.sysml`` file.

    Raises:
        SystemExit: If *only* names a folder that does not exist.
    """
    dirs = [
        directory
        for corpus in CORPUS_DIRS
        for directory in sorted(corpus.iterdir())
        if directory.is_dir() and any(directory.glob("*.sysml"))
    ]
    if only is None:
        return dirs
    chosen = []
    matched = set()
    for directory in dirs:
        relative = directory.relative_to(MODELS_DIR).as_posix()
        if directory.name in only or relative in only:
            chosen.append(directory)
            matched.update({directory.name, relative})
    missing = set(only) - matched
    if missing:
        sys.exit(f"unknown model(s): {', '.join(sorted(missing))}")
    return chosen


def _targets(model_dir: Path) -> list[str]:
    """Enumerate the qualified names to sweep in *model_dir*.

    Args:
        model_dir: Directory containing the SysML model.

    Returns:
        Every top-level part usage if the model declares any, otherwise
        every state definition; sorted.

    Raises:
        ValueError: If the model fails to load with diagnostic errors.
    """
    model = load_model(model_dir)
    parts = sorted(
        str(usage.qualified_name) for usage in top_level_part_usages(model)
    )
    if parts:
        return parts
    return sorted(
        str(state_def.qualified_name) for state_def in state_definitions(model)
    )


def _python_arguments(model_dir: Path) -> list[str]:
    """Return ``--python <file>`` when *model_dir* ships exactly one.

    Args:
        model_dir: Directory containing the SysML model.

    Returns:
        The CLI arguments forwarding the folder's single Python file,
        or an empty list.
    """
    py_files = sorted(model_dir.glob("*.py"))
    if len(py_files) == 1:
        return ["--python", str(py_files[0])]
    return []


def _invoke(command: list[str]) -> tuple[bool, str]:
    """Run *command* and return ``(ok, detail)``.

    Args:
        command: The full CLI command line.

    Returns:
        ``ok`` is whether the command exited 0. ``detail`` is the last
        stderr line on failure (the CLI's ``error: ...`` report) and
        the last stdout line on success (the run's closing
        ``clock=... status=...`` summary).
    """
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=600
    )
    if completed.returncode != 0:
        lines = completed.stderr.strip().splitlines()
        detail = lines[-1] if lines else f"exit code {completed.returncode}"
        return False, detail
    lines = completed.stdout.strip().splitlines()
    return True, lines[-1] if lines else ""


def _stage_result(
    label: str,
    stage: str,
    ok: bool,
    detail: str,
    expected: ExpectedFailure | None,
) -> Result:
    """Verdict for one stage, honoring ``EXPECTED_FAILURES`` strictly.

    Args:
        label: The target's report label.
        stage: The stage the verdict is for, ``build`` or ``run``.
        ok: Whether the CLI invocation exited 0.
        detail: The invocation's summary or error line.
        expected: The target's expected-failure entry, if any.

    Returns:
        The stage's :class:`Result`: a failure at a recorded stage
        counts as ok, and a recorded stage that passes counts as a
        failure so a stale entry turns the sweep red.
    """
    if expected is not None and stage in expected.stages:
        if ok:
            return Result(
                label,
                stage,
                False,
                "expected to fail but passed; update EXPECTED_FAILURES",
            )
        return Result(
            label, stage, True, f"expected failure: {expected.reason}"
        )
    return Result(label, stage, ok, detail)


def _sweep_target(
    model_dir: Path,
    element_qn: str,
    until: float,
    max_steps: int,
) -> list[Result]:
    """Build and run one target through the CLI.

    The two verbs are independent checks, so both always run: a build
    failure never hides the run verdict.

    Args:
        model_dir: Directory containing the SysML model.
        element_qn: Qualified name of the part usage or state
            definition to sweep.
        until: Simulated-time bound forwarded to ``quake run --until``.
        max_steps: Macro-step cap forwarded to ``quake run
            --max-steps``.

    Returns:
        One :class:`Result` per stage, build first.
    """
    relative = model_dir.relative_to(MODELS_DIR).as_posix()
    label = f"{relative}::{element_qn.split('::')[-1]}"
    expected = EXPECTED_FAILURES.get(label)
    python_arguments = _python_arguments(model_dir)

    build_dir = BUILD_ROOT / relative / element_qn.replace("::", ".")
    build_command = [
        sys.executable,
        "-m",
        "sysmlc.cli",
        "quake",
        "build",
        str(model_dir),
        "-e",
        element_qn,
        "-o",
        str(build_dir),
        *python_arguments,
    ]
    build_ok, build_detail = _invoke(build_command)

    run_command = [
        sys.executable,
        "-m",
        "sysmlc.cli",
        "quake",
        "run",
        str(model_dir),
        "-e",
        element_qn,
        "--until",
        str(until),
        "--max-steps",
        str(max_steps),
        *python_arguments,
    ]
    run_ok, run_detail = _invoke(run_command)

    return [
        _stage_result(label, "build", build_ok, build_detail, expected),
        _stage_result(label, "run", run_ok, run_detail, expected),
    ]


def main() -> int:
    """Sweep the selected models; return an exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Build and run every showcase and sm-examples model "
            "through the quake CLI."
        )
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="MODEL",
        help=(
            "sweep a subset (folder names, e.g. thermostat sm03-guard; "
            "corpus-qualified names like showcase/furuta-pendulum "
            "disambiguate)"
        ),
    )
    parser.add_argument(
        "--until",
        type=float,
        default=2.0,
        help="simulated-time bound per run (default: %(default)s)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=5000,
        help="macro-step cap per run (default: %(default)s)",
    )
    args = parser.parse_args()

    configure_logging("WARNING")

    results: list[Result] = []
    for model_dir in _model_dirs(args.only):
        relative = model_dir.relative_to(MODELS_DIR).as_posix()
        try:
            element_qns = _targets(model_dir)
        except ValueError as error:
            results.append(Result(relative, "load", False, str(error)))
            print(f"{relative}: load FAILED: {error}")
            continue
        if not element_qns:
            detail = "no top-level part usage or state definition"
            results.append(Result(relative, "load", False, detail))
            print(f"{relative}: load FAILED: {detail}")
            continue
        print(f"{relative} ({len(element_qns)} target(s))", flush=True)
        for element_qn in element_qns:
            build_result, run_result = _sweep_target(
                model_dir, element_qn, args.until, args.max_steps
            )
            results.extend([build_result, run_result])
            leaf = element_qn.split("::")[-1]
            if build_result.ok and run_result.ok:
                print(f"    {leaf}: ok  {run_result.detail}")
            else:
                for stage_result in (build_result, run_result):
                    status = "ok" if stage_result.ok else "FAILED"
                    print(
                        f"    {leaf} {stage_result.stage}: {status}  "
                        f"{stage_result.detail}"
                    )

    failed = [result for result in results if not result.ok]
    print("\n=== summary ===")
    print(f"  {len(results) - len(failed)}/{len(results)} checks ok")
    for result in failed:
        print(f"  FAILED {result.label} ({result.stage}): {result.detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
