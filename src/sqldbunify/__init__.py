# SPDX-FileCopyrightText: 2026 Tsyganov Pavel
# SPDX-License-Identifier: MIT

from .connection import ConnectionHook, create_async_engine_with_pool, create_session_factory, dispose_engine
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

__version__ = "0.1.0"

__all__ = [
    "ConnectionHook",
    "create_async_engine_with_pool",
    "create_session_factory",
    "dispose_engine",

    "DAOError",
    "DAOConfigurationError",
    "DAOConnectionError",
    "DAOQueryError",
    "DAOValidationError",

    "FilterType",
    "FilterTuple",
    "FilterGroup",
    "ReturnMode",
    "JoinType",
    "OperatorType",
    "LogicType",
]
