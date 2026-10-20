# SPDX-FileCopyrightText: 2026 Tsyganov Pavel
# SPDX-License-Identifier: MIT

"""
sqldbunify — Universal async DAO wrapper for SQLAlchemy.
"""

from importlib.metadata import PackageNotFoundError, version

from .base_dao import BaseDAO
from .connection import (
    SQLITE_DEFAULT_PRAGMAS,
    ConnectionHook,
    create_async_engine_with_pool,
    create_session_factory,
    dispose_engine,
)
from .exceptions import (
    DAOConfigurationError,
    DAOConnectionError,
    DAOError,
    DAOQueryError,
    DAOValidationError,
)
from .types import (
    FilterGroup,
    FilterTuple,
    FilterType,
    JoinType,
    LogicType,
    OperatorType,
    ReturnMode,
)

try:
    __version__ = version("sqldbunify")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    # Core
    "BaseDAO",
    "create_async_engine_with_pool",
    "create_session_factory",
    "dispose_engine",
    # Exceptions
    "DAOError",
    "DAOConfigurationError",
    "DAOConnectionError",
    "DAOQueryError",
    "DAOValidationError",
    # Types
    "ConnectionHook",
    "FilterType",
    "FilterTuple",
    "FilterGroup",
    "ReturnMode",
    "JoinType",
    "OperatorType",
    "LogicType",
    "SQLITE_DEFAULT_PRAGMAS",
    # Metadata
    "__version__",
]
