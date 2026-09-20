# SPDX-FileCopyrightText: 2026 Tsyganov Pavel
# SPDX-License-Identifier: MIT

"""
Exceptions raised by sqldbunify.

All library-specific exceptions inherit from DAOError, so users can catch
the whole family with a single `except DAOError:`.
"""


class DAOError(RuntimeError):
    """Base exception for all sqldbunify errors."""


class DAOConnectionError(DAOError):
    """Raised when a database connection cannot be established or is lost."""


class DAOQueryError(DAOError):
    """Raised when a query fails to execute (syntax, constraints, etc.)."""


class DAOValidationError(DAOError):
    """Raised when input data is invalid (bad filter format, missing fields)."""


class DAOConfigurationError(DAOError):
    """Raised when the DAO is misconfigured (e.g., session factory not set)."""


__all__ = [
    "DAOError",
    "DAOConnectionError",
    "DAOQueryError",
    "DAOValidationError",
    "DAOConfigurationError",
]
