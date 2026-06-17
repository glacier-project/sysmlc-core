import syside

from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import iter_elements
from tests.backends.test_sm_examples import (  # noqa: F401  (re-exported)
    SM_EXAMPLES,
    SM_EXAMPLES_BY_DIR,
    SM_EXAMPLES_DIR,
    SmExample,
)


def _discover_all_state_def_qns() -> list[tuple[SmExample, str]]:
    """Eagerly enumerate every ``StateDefinition`` QN in every sm-example.

    Used at pytest collection time to parametrize corpus-wide
    invariants over every state def declared in any example model.

    Returns:
        Pairs of ``(example, state_def_qn)`` sorted within each
        example's QN list for stable test-id ordering.
    """
    pairs: list[tuple[SmExample, str]] = []
    for example in SM_EXAMPLES:
        model = load_model(example.model_dir)
        qns = sorted(
            str(sd.qualified_name)
            for sd in iter_elements(model, syside.StateDefinition)
        )
        pairs.extend((example, qn) for qn in qns)
    return pairs


ALL_EXAMPLE_QN_PAIRS: list[tuple[SmExample, str]] = (
    _discover_all_state_def_qns()
)
