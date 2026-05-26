from dataclasses import dataclass
from pathlib import Path

import pytest
import syside

from sysml2frost.loader import load_syside_model

SM_EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "models" / "sm-examples"


@dataclass(frozen=True)
class SmExample:
    """One entry in the SysML state-machine examples collection.

    Attributes:
        dir_name: Folder under ``models/sm-examples/`` holding the
            example's ``.sysml`` sources.
        state_def_qn: Qualified name of the ``state def`` translated
            by the sismic generator.
    """

    dir_name: str
    state_def_qn: str

    @property
    def model_dir(self) -> Path:
        return SM_EXAMPLES_DIR / self.dir_name


SM_EXAMPLES: list[SmExample] = [
    SmExample("sm01-helloworld", "SM01::Machine"),
    SmExample("sm02-event-trigger", "SM02::Machine"),
]

SM_EXAMPLES_BY_DIR: dict[str, SmExample] = {e.dir_name: e for e in SM_EXAMPLES}


@pytest.fixture(scope="module", params=SM_EXAMPLES, ids=lambda e: e.dir_name)
def sm_example(request: pytest.FixtureRequest) -> SmExample:
    """Yield each registered sm-example, one per test invocation."""
    return request.param


@pytest.fixture(scope="module")
def sm_example_model(sm_example: SmExample) -> syside.Model:
    """Load the SysML model for the currently-parametrized example."""
    return load_syside_model(sm_example.model_dir)
