from sysmlc.backends.statix.serialize import _env


def test_environment_does_not_autoescape() -> None:
    # HTML-escaping would corrupt C operators like && < >.
    assert _env.autoescape is False


def test_all_templates_loadable() -> None:
    # Templates are runtime data shipped in the wheel; loading each by name
    # through the backend's own loader guards against a packaging omission.
    for name in (
        "cmakelists.txt.j2",
        "runner.c.j2",
        "machine.h.j2",
        "machine.c.j2",
    ):
        # Raises TemplateNotFound if the template is missing.
        _env.get_template(name)
