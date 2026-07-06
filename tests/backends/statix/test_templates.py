from sysmlc.backends.statix.serialize import _env


def test_environment_does_not_autoescape() -> None:
    # HTML-escaping would corrupt C operators like && < >.
    assert _env.autoescape is False
