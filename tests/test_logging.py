"""Package logging: plugins log through the package handler."""

from __future__ import annotations

import logging

from sysmlc.logging import PACKAGE_LOGGER_NAME, configure_logging


def test_plugin_packages_share_the_package_handler() -> None:
    plugin = logging.getLogger("sysmlc_test_plugin")
    try:
        package = configure_logging("INFO", packages=["sysmlc_test_plugin"])
        assert package is logging.getLogger(PACKAGE_LOGGER_NAME)
        assert plugin.level == logging.INFO
        shared = list(plugin.handlers)
        assert len(shared) == 1
        assert isinstance(shared[0], logging.StreamHandler)
        assert shared[0] in package.handlers
        # Still propagating, so a host's own handlers keep seeing them.
        assert plugin.propagate
        configure_logging("INFO", packages=["sysmlc_test_plugin"])
        assert plugin.handlers == shared
    finally:
        for handler in list(plugin.handlers):
            plugin.removeHandler(handler)
        plugin.setLevel(logging.NOTSET)
