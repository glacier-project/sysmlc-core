from __future__ import annotations

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml import metadata

EXTERNAL_MODULE_QN = "ExternalModuleBinding::ExternalModule"


def external_module_definition(
    model: syside.Model,
) -> syside.MetadataDefinition | None:
    """Resolve the bundled ``ExternalModule`` metadata def, or None if absent.

    The definition ships as a bundled library, so it is present in every
    model loaded through :func:`sysmlc.sysml.loading.load_model`; ``None``
    covers models assembled through other paths.
    """
    try:
        return metadata.resolve_metadata_definition(model, EXTERNAL_MODULE_QN)
    except ValueError:
        return None


def _extract_literal_string(value_element: syside.Element) -> str | None:
    """Extract a raw string value from a syside AST node."""
    if isinstance(value_element, syside.LiteralString):
        return value_element.value
    return None


def _extract_files_and_lang(
    metadata_usage: syside.MetadataUsage,
) -> tuple[list[str], str | None]:
    """Extract file paths and the `lang` attribute from a metadata usage."""
    file_paths: list[str] = []
    extracted_lang: str | None = None

    for feature in metadata_usage.owned_members.collect():
        if not isinstance(feature, syside.Feature) or not feature.name:
            continue

        for rel in feature.owned_relationships.collect():
            if not isinstance(rel, syside.FeatureValue) or rel.value is None:
                continue

            if feature.name == "lang":
                extracted_lang = _extract_literal_string(rel.value)
            elif feature.name == "files":
                value = _extract_literal_string(rel.value)
                if value:
                    file_paths.append(value)
                elif isinstance(rel.value, syside.OperatorExpression):
                    for operand in rel.value.operands.collect():
                        operand_value = _extract_literal_string(operand)
                        if operand_value:
                            file_paths.append(operand_value)

    return file_paths, extracted_lang


def _validate_single_file_constraint(
    file_paths: list[str],
    element: syside.Element,
) -> None:
    """Reject metadata that declares more than one file.

    TODO: lift this restriction once multi-file modules are supported.
    """
    if len(file_paths) <= 1:
        return

    element_qn = str(
        getattr(
            element, "qualified_name", getattr(element, "name", "<anonymous>")
        )
    )
    raise UnsupportedConstructError(
        f"The @ExternalModule metadata on element {element_qn!r} "
        f"specifies {len(file_paths)} files: {file_paths!r}. "
        "Currently, only a single file per module is supported.",
        node=element,
    )


def get_external_filepath_from_metadata(
    model: syside.Model,
    target_lang: str = "python",
) -> tuple[str, ...] | None:
    """Locate @ExternalModule metadata in the model and return its file paths.

    ``ExternalModule`` ships as a bundled library metadata definition
    model apply it with ``@ExternalModule { ... }``
    without declaring or importing it.

    Args:
        model: The loaded syside Model instance.
        target_lang: The target language filter (default: "python").

    Returns:
        A tuple of relative file paths, or None if no matching metadata was found.

    Raises:
        UnsupportedConstructError: If more than one @ExternalModule
            application matches `target_lang` in the model, or if a single
            application lists more than one file (single-file restriction).
    """
    definition = external_module_definition(model)
    if definition is None:
        return None

    found_paths: list[str] = []
    source_elements: list[syside.Element] = []

    for element, usage in metadata.elements_with_metadata(
        model, syside.Element, definition
    ):
        file_paths, lang = _extract_files_and_lang(usage)
        if not file_paths:
            continue
        if lang and lang.lower() != target_lang.lower():
            continue

        _validate_single_file_constraint(file_paths, element)
        found_paths.extend(file_paths)
        source_elements.append(element)

    if not found_paths:
        return None

    if len(source_elements) > 1:
        qualified_names = [
            str(getattr(e, "qualified_name", getattr(e, "name", "<anonymous>")))
            for e in source_elements
        ]
        raise UnsupportedConstructError(
            f"Found {len(source_elements)} @ExternalModule declarations "
            f"across model elements: {qualified_names}. "
            "Currently, only one global @ExternalModule per model is supported."
        )

    return tuple(found_paths)
