"""Compile-local registries for generated identifiers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from collections.abc import Callable


class NameRegistry:
    """Assign stable identifiers within one target naming scope.

    Assignments depend on request order. Callers reserve fixed names first
    and request symbols in a deterministic order. Source names and semantic
    identities are never modified.
    """

    def __init__(
        self,
        candidate: Callable[[str, int], str],
        *,
        key: Callable[[str], str] = str,
    ) -> None:
        """Configure target spelling and comparison rules.

        Args:
            candidate: Return a valid target identifier from a preferred
                spelling and a nonnegative attempt number. Attempt zero
                should preserve an already valid spelling. Increasing
                attempts must eventually produce unoccupied comparison keys.
            key: Normalize an identifier for collision comparisons, for
                example ``str.casefold`` for case-insensitive names.
        """
        self._candidate = candidate
        self._key = key
        self._used: dict[str, str | None] = {}
        self._assigned: dict[str, str] = {}

    def reserve(self, *names: str) -> None:
        """Reserve fixed names before allocating generated symbols.

        Args:
            *names: Spellings owned by fixed interfaces or declarations.

        Raises:
            UnsupportedConstructError: A generated symbol already owns a
                name. No reservations from this call are applied on failure.
        """
        keys = [self._key(name) for name in names]
        for name, key in zip(names, keys, strict=True):
            if self._used.get(key) is not None:
                raise UnsupportedConstructError(
                    f"externally dictated name {name!r} was reserved after "
                    "generated symbols were allocated"
                )
        self._used.update(dict.fromkeys(keys))

    def available(self, name: str) -> bool:
        """Whether a preferred spelling can be assigned unchanged."""
        return (
            self._candidate(name, 0) == name
            and self._key(name) not in self._used
        )

    def assign(self, identity: str, preferred: str) -> str:
        """Assign an unoccupied identifier, or return its previous assignment.

        Args:
            identity: Identity of the generated symbol within this registry.
                Distinct roles derived from one source element need distinct
                identities.
            preferred: Readable spelling passed to the target candidate rule.

        Returns:
            The assigned identifier. Later requests for the same identity
            return this spelling regardless of their preferred argument.
        """
        if identity in self._assigned:
            return self._assigned[identity]
        attempt = 0
        name = self._candidate(preferred, attempt)
        while self._key(name) in self._used:
            attempt += 1
            name = self._candidate(preferred, attempt)
        self._used[self._key(name)] = identity
        self._assigned[identity] = name
        return name
