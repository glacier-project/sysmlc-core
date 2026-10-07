from pathlib import Path

import pytest
import syside

from tests import _load_inline_model
from tests.test_recording import RecordingBuilder


@pytest.fixture
def recording_builder() -> RecordingBuilder:
    return RecordingBuilder()


@pytest.fixture
def contract_model(tmp_path: Path) -> syside.Model:
    return _load_inline_model(
        tmp_path,
        """
        package Contracts {
            private import ScalarValues::*;
            state def Machine {
                in attribute threshold : Real default 2.0;
                out attribute report : Real := 0.0;
                inout attribute level : Real := 1.0;
                assert constraint levelPositive { level >= 0.0 }
                assert constraint thresholdPositive { threshold > 0.0 }
                entry; then idle;
                state idle;
            }
        }
    """,
    )
