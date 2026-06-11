import pytest

from tests.recording import RecordingBuilder


@pytest.fixture
def recording_builder() -> RecordingBuilder:
    return RecordingBuilder()
