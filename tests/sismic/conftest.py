from dataclasses import dataclass
from pathlib import Path

import syside

from sysml2frost.explore import iter_model_elements
from sysml2frost.loader import load_syside_model

SM_EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "models" / "sm-examples"


@dataclass(frozen=True)
class SmExample:
    """One entry in the SysML state-machine examples collection.

    Attributes:
        dir_name: Folder under ``models/sm-examples/`` holding the
            example's ``.sysml`` sources.
    """

    dir_name: str

    @property
    def model_dir(self) -> Path:
        return SM_EXAMPLES_DIR / self.dir_name


SM_EXAMPLES: list[SmExample] = [
    SmExample("sm01-helloworld"),
    SmExample("sm02-event-trigger"),
    SmExample("sm03-guard"),
    SmExample("sm04-assignment"),
    SmExample("sm05-chained-references"),
    SmExample("sm06-transition-effect"),
    SmExample("sm07-firing-order"),
    SmExample("sm08-nested-composite"),
    SmExample("sm09-parallel"),
    SmExample("sm10-done"),
]

SM_EXAMPLES_BY_DIR: dict[str, SmExample] = {e.dir_name: e for e in SM_EXAMPLES}


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
        model = load_syside_model(example.model_dir)
        qns = sorted(
            str(sd.qualified_name)
            for sd in iter_model_elements(model, syside.StateDefinition)
        )
        pairs.extend((example, qn) for qn in qns)
    return pairs


ALL_EXAMPLE_QN_PAIRS: list[tuple[SmExample, str]] = (
    _discover_all_state_def_qns()
)
