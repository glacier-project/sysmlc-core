import pytest

from tests.test_recording import RecordingBuilder


@pytest.fixture
def recording_builder() -> RecordingBuilder:
    return RecordingBuilder()
