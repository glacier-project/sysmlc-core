"""Pins the exact lowered C for every guard/action across the supported models.

A behavioural conformance test can miss an expression bug that happens to yield
the same result (``x / 2`` vs ``x * 2`` both settle in the same state), so this
compares the generated *text* directly. It covers all of sm03's guard variants
and every assignment effect in sm04/sm05/sm06 -- the expression-bearing subset.
"""

import pytest

from sysmlc.backends.statix.builder import build_statix

# (stem, qn) -> (expected guard expressions, expected action statements).
_EXPECTED = {
    # sm03 -- one guarded transition per state def.
    ("sm03", "SM03::MachineLiteralTrue"): (["true"], []),
    ("sm03", "SM03::MachineLiteralFalse"): (["false"], []),
    ("sm03", "SM03::MachineRef"): (["ctx->enabled"], []),
    ("sm03", "SM03::MachineNot"): (["!ctx->enabled"], []),
    ("sm03", "SM03::MachineUnaryMinus"): (["-ctx->x < 0"], []),
    ("sm03", "SM03::MachineAnd"): (["ctx->a && ctx->b"], []),
    ("sm03", "SM03::MachineOr"): (["ctx->a || ctx->b"], []),
    ("sm03", "SM03::MachineEq"): (["ctx->x == 1"], []),
    ("sm03", "SM03::MachineNeq"): (["ctx->x != 0"], []),
    ("sm03", "SM03::MachineLt"): (["ctx->x < 2"], []),
    ("sm03", "SM03::MachineLe"): (["ctx->x <= 1"], []),
    ("sm03", "SM03::MachineGt"): (["ctx->x > 0"], []),
    ("sm03", "SM03::MachineGe"): (["ctx->x >= 1"], []),
    ("sm03", "SM03::MachineArithPlus"): (["ctx->x + 1 > 1"], []),
    ("sm03", "SM03::MachineArithMinus"): (["ctx->x - 1 > 0"], []),
    ("sm03", "SM03::MachineArithMul"): (["ctx->x * 2 > 1"], []),
    ("sm03", "SM03::MachineArithDiv"): (["ctx->x / 2 > 1"], []),
    ("sm03", "SM03::MachineRealLiteral"): (["ctx->x > 0.5"], []),
    ("sm03", "SM03::MachineLogicalChain"): (["ctx->a && ctx->b || ctx->c"], []),
    ("sm03", "SM03::MachineLowerPrecLhs"): (
        ["(ctx->a || ctx->b) && ctx->c"],
        [],
    ),
    ("sm03", "SM03::MachineLeftAssocRhs"): (["ctx->x - (1 - 2) > 0"], []),
    # sm04 -- entry/exit assignment effects.
    ("sm04", "SM04::MachineEntryIncrement"): (
        [],
        ["ctx->counter = ctx->counter + 1;"],
    ),
    ("sm04", "SM04::MachineExitDecrement"): (
        [],
        ["ctx->counter = ctx->counter - 1;"],
    ),
    ("sm04", "SM04::MachineMultiEntry"): (
        [],
        ["ctx->a = 1;", "ctx->b = ctx->a + 2;"],
    ),
    ("sm04", "SM04::MachineEntryAndExit"): (
        [],
        ["ctx->entered = ctx->entered + 1;", "ctx->exited = ctx->exited + 1;"],
    ),
    ("sm04", "SM04::MachineEntryShorthand"): (
        [],
        ["ctx->counter = ctx->counter + 1;"],
    ),
    ("sm04", "SM04::MachineExitShorthand"): (
        [],
        ["ctx->counter = ctx->counter - 1;"],
    ),
    # sm05 -- chained references in guards and effects.
    ("sm05", "SM05::MachineChainGuard"): (["ctx->pt.x > 0.0"], []),
    ("sm05", "SM05::MachineChainNested"): (["ctx->box.inner.z > 0.0"], []),
    ("sm05", "SM05::MachineChainAssign"): ([], ["ctx->reached = ctx->pt.x;"]),
    # sm06 -- transition effects.
    ("sm06", "SM06::MachineEffect"): ([], ["ctx->counter = ctx->counter + 1;"]),
    ("sm06", "SM06::MachineEffectMulti"): (
        [],
        ["ctx->a = 1;", "ctx->b = ctx->a + 2;"],
    ),
}


@pytest.mark.parametrize("key", list(_EXPECTED), ids=lambda k: k[1])
def test_expression_fidelity(sm_models: dict, key: tuple[str, str]) -> None:
    stem, qn = key
    expected_guards, expected_actions = _EXPECTED[key]
    program = build_statix(sm_models[stem], qn)
    assert [g.expr for g in program.guards] == expected_guards
    got_actions = [s for a in program.actions for s in a.statements]
    assert got_actions == expected_actions
