# SPDX-FileCopyrightText: 2026 Tsyganov Pavel
# SPDX-License-Identifier: MIT

"""
Internal logger for sqldbunify.

The library never configures logging on its own — that's the
application's responsibility. It only obtains a logger named
``"sqldbunify"`` and emits records through it. Users control output
via the standard :mod:`logging` module.

Examples:
    Enable logs for the whole application::

        import logging
        logging.basicConfig(level=logging.DEBUG)

    Enable logs only for sqldbunify::

        import logging
        logging.getLogger("sqldbunify").setLevel(logging.DEBUG)
        logging.getLogger("sqldbunify").addHandler(logging.StreamHandler())

    Reduce verbosity of sqldbunify while keeping other logs at DEBUG::

        import logging
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("sqldbunify").setLevel(logging.WARNING)
"""

import logging

logger = logging.getLogger("sqldbunify")
"""
Module-level logger used across the library.

Named ``"sqldbunify"``, so users can target it precisely::

    logging.getLogger("sqldbunify").setLevel(logging.DEBUG)

The logger propagates records to the root logger by default and has no handlers of its own.
"""

if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
    logger.addHandler(logging.NullHandler())
"""
Attach a :class:`~logging.NullHandler` to silence the "No handlers
could be found" warning when the application hasn't configured logging.

This is a library best practice (see :pep:`282` and the `logging
cookbook <https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library>`_):
the library must not print anything on its own, but also must not
complain when nobody is listening.

Applications that configure logging (via ``basicConfig``,
``dictConfig``, or by adding handlers manually) will see records
normally — the NullHandler only swallows records when there is no other handler.
"""


__all__ = ["logger"]
