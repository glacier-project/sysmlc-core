from __future__ import annotations

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.queries import iter_elements

_TARGET_METADATA_NAME = "ExternalModule"


def _extract_literal_string(value_element: syside.Element) -> str | None:
    """Extract a raw string value from a syside AST node."""
    if isinstance(value_element, syside.LiteralString):
        val = value_element.value
        return str(val) if val is not None else None
    return None


def _get_metadata_name(member: syside.MetadataUsage) -> str | None:
    """Resolve the metadata definition name from a MetadataUsage node."""
    meta_name = getattr(member, "name", None) or getattr(
        getattr(member, "metadata_definition", None), "name", None
    )
    if meta_name:
        return str(meta_name)

    typings = member.owned_typings.collect()
    if typings and hasattr(typings[0], "type"):
        name = getattr(typings[0].type, "name", None)
        return str(name) if name is not None else None

    return None


def _extract_files_and_lang(
    metadata: syside.MetadataUsage,
) -> tuple[list[str], str | None]:
    """Extract file paths and language attribute from the metadata usage."""
    file_paths: list[str] = []
    extracted_lang: str | None = None

    for feature in metadata.owned_members.collect():
        if not isinstance(feature, syside.Feature) or not feature.name:
            continue

        for rel in feature.owned_relationships.collect():
            if not (
                isinstance(rel, syside.FeatureValue) and rel.value is not None
            ):
                continue

            if feature.name == "lang":
                extracted_lang = _extract_literal_string(rel.value)

            elif feature.name == "files":
                val = _extract_literal_string(rel.value)
                if val:
                    file_paths.append(val)
                elif isinstance(rel.value, syside.OperatorExpression):
                    for operand in rel.value.operands.collect():
                        v = _extract_literal_string(operand)
                        if v:
                            file_paths.append(v)

    return file_paths, extracted_lang


def _validate_single_file_constraint(
    file_paths: list[str],
    element: syside.Element,
) -> None:
    """Validation guard: Enforces single file constraint.

    Remove or bypass this validation step in the future to enable multi-file support.
    """
    if len(file_paths) > 1:
        element_qn = str(
            getattr(
                element,
                "qualified_name",
                getattr(element, "name", "<anonymous>"),
            )
        )
        raise UnsupportedConstructError(
            f"The @{_TARGET_METADATA_NAME} metadata on element {element_qn!r} "
            f"specifies {len(file_paths)} files: {file_paths!r}. "
            "Currently, only a single file per module is supported.",
            node=element,
        )


def _get_paths(
    element: syside.Element,
    metadata: syside.MetadataUsage,
    target_lang: str,
) -> list[str]:
    """Extract path list for matching language and perform current constraint validations."""
    file_paths, lang = _extract_files_and_lang(metadata)

    # Filter out if language doesn't match target (case-insensitive)
    if lang and lang.lower() != target_lang.lower():
        return []

    if not file_paths:
        return []

    _validate_single_file_constraint(file_paths, element)
    return file_paths


def get_external_filepath_from_metadata(
    model: syside.Model,
    target_lang: str = "python",
) -> tuple[str, ...] | None:
    """Locate @ExportModule metadata in the model and return the declared file paths.

    Args:
        model: The loaded syside Model instance.
        target_lang: The target language filter (default: "python").

    Returns:
        A tuple of relative file paths, or None if no matching metadata was found.

    Raises:
        UnsupportedConstructError: If multiple metadata instances exist globally or if
            more than 1 file is attached (due to single-file restriction).
    """
    found_paths: list[str] = []
    source_elements: list[syside.Element] = []

    for element in iter_elements(model, syside.Element):
        for member in element.owned_elements.collect():
            if not isinstance(member, syside.MetadataUsage):
                continue

            if _get_metadata_name(member) == _TARGET_METADATA_NAME:
                paths = _get_paths(element, member, target_lang)
                if paths:
                    found_paths.extend(paths)
                    source_elements.append(element)

    if not found_paths:
        return None

    if len(source_elements) > 1:
        pkgs = [
            str(getattr(e, "qualified_name", getattr(e, "name", "<anonymous>")))
            for e in source_elements
        ]
        raise UnsupportedConstructError(
            f"Found {len(source_elements)} @{_TARGET_METADATA_NAME} declarations across model elements: {pkgs}. "
            "Currently, only one global @ExportModule per model is supported."
        )

    return tuple(found_paths)
