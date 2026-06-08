from __future__ import annotations

import logging

from sysmlc.logging_utils import configure_logging, setup_logging

_package_logger = logging.getLogger("sysmlc")
_package_logger.addHandler(logging.NullHandler())

__all__ = ["configure_logging", "setup_logging"]
