"""Probe-based SysML quantity parsing for value overrides.

Quantity strings (e.g. ``"90 [s]"``) are parsed by compiling them as
declarations inside a tiny throw-away SysML package, then walking the
resulting AST to extract the magnitude literal, unit qualified name, and
unit-kind qualified name. This gives full SysML parsing — unit aliases,
scientific notation — for free, without duplicating the language grammar.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import syside

from sysmlc.errors import ValuesError
from sysmlc.semantics.statemachine.triggers import evaluate_to_number
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import iter_elements

LITERAL_NODE_TYPES = (
    syside.LiteralBoolean,
    syside.LiteralInteger,
    syside.LiteralRational,
    syside.LiteralString,
)

_PROBE_TEMPLATE = """package __SysmlcValuesProbe {{
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::*;
{declarations}
}}
"""


@dataclass(frozen=True)
class Quantity:
    """A parsed SysML quantity override."""

    magnitude: float
    si: float
    unit_qn: str
    kind_qn: str


class QuantityProbe:
    """Parse SysML quantity strings by compiling them as a tiny model.

    All quantity-string overrides are declared in one probe package
    (``attribute __v0 = 90 [s];``), loaded lazily once, giving full SysML
    parsing — unit aliases, scientific notation — plus the unit referent
    for the kind check and the SI value for conversion.
    """

    def __init__(self, element_qn: str, strings: list[tuple[str, str]]) -> None:
        """``strings`` holds (attribute name, quantity text) pairs."""
        self._element_qn = element_qn
        self._strings = strings
        self._parsed: dict[str, Quantity] | None = None

    def quantity(self, name: str) -> Quantity:
        """Return the parsed :class:`Quantity` for *name*."""
        if self._parsed is None:
            self._parsed = self._parse()
        return self._parsed[name]

    def _parse(self) -> dict[str, Quantity]:
        names = [name for name, _ in self._strings]
        declarations = "\n".join(
            f"    attribute __v{i} = {text};"
            for i, (_, text) in enumerate(self._strings)
        )
        snippet = _PROBE_TEMPLATE.format(declarations=declarations)
        out: dict[str, Quantity] = {}
        with tempfile.TemporaryDirectory() as workdir:
            probe_file = Path(workdir) / "values_probe.sysml"
            probe_file.write_text(snippet)
            try:
                probe_model = load_model(workdir)
            except ValueError as error:
                raise ValuesError(
                    f"a quantity override for {self._element_qn!r} is not "
                    f"valid SysML: {error}"
                ) from error
            parsed = {
                e.name: e
                for e in iter_elements(probe_model, syside.AttributeUsage)
                if e.name and e.name.startswith("__v")
            }
            compiler = syside.Compiler()
            stdlib = syside.Stdlib(probe_model.index)
            for index, name in enumerate(names):
                expr = parsed[f"__v{index}"].feature_value_expression
                assert expr is not None
                magnitude, unit_qn, kind_qn = quantity_parts(
                    expr, f"the override for {name!r}"
                )
                si = evaluate_to_number(expr, compiler, stdlib)
                if si is None:
                    raise ValuesError(
                        f"the override for {name!r} does not evaluate to "
                        "a number"
                    )
                assert isinstance(magnitude, LITERAL_NODE_TYPES)
                out[name] = Quantity(
                    magnitude=float(magnitude.value),
                    si=float(si),
                    unit_qn=unit_qn,
                    kind_qn=kind_qn,
                )
        return out


def quantity_parts(
    expr: syside.Expression, what: str
) -> tuple[syside.Element, str, str]:
    """Split a quantity expression into (magnitude literal, unit, kind)."""
    if (
        not isinstance(expr, syside.OperatorExpression)
        or expr.operator is not syside.Operator.Quantity
    ):
        raise ValuesError(
            f"{what} is not a measurement expression of the form "
            "'<number> [<unit>]'"
        )
    magnitude, unit = expr.operands.collect()
    referent = getattr(unit, "referent", None)
    types = referent.types.collect() if referent is not None else []
    if referent is None or not types:
        raise ValuesError(f"{what} has no resolvable measurement unit")
    return (
        magnitude,
        str(referent.qualified_name),
        str(types[0].qualified_name),
    )
