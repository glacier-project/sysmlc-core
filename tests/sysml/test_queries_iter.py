import syside

from sysmlc.sysml.queries import iter_elements


def test_iter_elements_finds_known_part_usages(
    model: syside.Model,
) -> None:
    usages = iter_elements(model, syside.PartUsage)
    usage_names = {usage.name for usage in usages}

    assert "qualityControl" in usage_names
    assert "rbKairosA" in usage_names
    assert "rbKairosB" in usage_names
