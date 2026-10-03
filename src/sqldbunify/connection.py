# SPDX-FileCopyrightText: 2026 Tsyganov Pavel
# SPDX-License-Identifier: MIT

"""
Engine and session factory helpers for sqldbunify.

Provides a unified way to create async SQLAlchemy engines with
database-specific pool settings, plus a session factory helper.
"""

import contextlib
import uuid
from typing import Any, Callable, Optional, Union

from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from .exceptions import DAOConfigurationError
from .logger import logger

# ============================================================
# Public type aliases
# ============================================================

ConnectionHook = Callable[[Any, ConnectionPoolEntry], None]
"""
Signature for ``on_connect`` / ``on_close`` callbacks.

Args:
    dbapi_connection: The raw DBAPI connection object (driver-specific).
    connection_record: The :class:`~sqlalchemy.pool.ConnectionPoolEntry`
        representing this connection in the pool. Use its ``info`` dict
        to attach persistent data (e.g., resources) that lives for the
        lifetime of the connection.
"""


# ============================================================
# Default SQLite PRAGMAs
# ============================================================

SQLITE_DEFAULT_PRAGMAS: dict[str, Any] = {
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    "cache_size": -64000,
    "temp_store": "MEMORY",
    "foreign_keys": "ON",
    "busy_timeout": 30000,
}
"""
Sensible default PRAGMAs for SQLite connections.

Applied to every SQLite connection unless overridden via the
``sqlite_pragmas`` argument of :func:`create_async_engine_with_pool`.
To disable a specific PRAGMA, pass ``None`` as its value:
``{"foreign_keys": None}``.

Full PRAGMA reference
---------------------

PRAGMA statements are a SQLite-specific extension used to modify the
operation of the SQLite library or to query internal (non-table) data.
Unknown PRAGMAs are silently ignored, so typos go unnoticed.

Below is a categorized reference of the most commonly used PRAGMAs.
For the complete and authoritative list, see the official documentation:
https://www.sqlite.org/pragma.html

**Concurrency & journaling**

- **journal_mode** — ``"WAL"``
Controls how SQLite journals transactions.
Values: ``"DELETE"`` (default rollback journal), ``"TRUNCATE"``
(truncate instead of delete), ``"PERSIST"`` (keep journal file),
``"MEMORY"`` (in-memory journal), ``"WAL"`` (write-ahead log, allows
concurrent readers and writers), ``"OFF"`` (no journal).
This is a persistent setting: it is stored in the database file.

- **synchronous** — ``"NORMAL"``
How often SQLite syncs to disk. Under ``WAL`` mode, ``"NORMAL"``
provides a good balance of safety and speed.
Values: ``"OFF"`` (no sync, fastest but risky), ``"NORMAL"``
(sync at critical moments), ``"FULL"`` (sync on every commit),
``"EXTRA"`` (like ``FULL`` plus directory sync).
Connection-level setting.

- **busy_timeout** — ``30000`` (30 seconds)
Milliseconds to wait for a locked database before raising
``SQLITE_BUSY``. SQLite's default is ``0`` (fail immediately).
Any non-negative integer is valid. Connection-level setting.

- **wal_autocheckpoint** — ``1000`` (default)
Pages threshold for automatic WAL checkpointing. When the WAL
reaches this many pages, SQLite automatically runs a checkpoint.
Values: any positive integer; ``0`` disables auto-checkpointing.
Connection-level setting.

**Data integrity**

- **foreign_keys** — ``"ON"``
Enforce ``FOREIGN KEY`` constraints. SQLite disables them by default,
which can lead to orphaned rows.
Values: ``"ON"``, ``"OFF"``. Connection-level setting.

- **recursive_triggers** — ``"OFF"`` (default)
Allow recursive firing of triggers.
Values: ``"ON"``, ``"OFF"``. Connection-level setting.

- **cell_size_check** — ``"OFF"`` (default)
Enable additional sanity checking on database b-tree pages as they
are read from disk. Detects corruption earlier at a small performance
cost. Values: ``"ON"``, ``"OFF"``. Connection-level setting.

**Performance & memory**

- **cache_size** — ``-64000`` (≈ 64 MB)
Page cache size. A positive value is the number of pages; a negative
value is the size in kibibytes. Connection-level setting.

- **temp_store** — ``"MEMORY"``
Where temporary tables and indices are stored.
Values: ``"DEFAULT"`` (compile-time default, usually file-based),
``"FILE"`` (on disk), ``"MEMORY"`` (in RAM, faster).
Connection-level setting.

- **mmap_size** — ``0`` (default)
Maximum number of bytes of the database file that may be
memory-mapped. ``0`` disables memory-mapped I/O.
Values: any non-negative integer. Connection-level setting.

- **cache_spill** — ``"ON"`` (default)
Allow the cache to spill to disk when it exceeds its size limit.
Values: ``"ON"``, ``"OFF"``, or an integer threshold.
Connection-level setting.

- **page_size** — ``4096`` (default)
Database page size. Must be set **before** any tables are created
(before the first ``VACUUM``). Persistent setting.

**Query planning & optimization**

- **analysis_limit** — ``0`` (no limit)
Limits the number of rows examined by ``ANALYZE`` on large databases.
Values: any non-negative integer; ``0`` means no limit.
Connection-level setting.

- **optimize** — (command, not a setting)
Runs ``ANALYZE`` on tables where it would be beneficial. Should be
invoked periodically, not per connection.
Usage: ``PRAGMA optimize;``

- **automatic_index** — ``"ON"`` (default)
Enable automatic creation of transient indices.
Values: ``"ON"``, ``"OFF"``. Connection-level setting.

**Maintenance & inspection**

- **integrity_check** — (command, not a setting)
Performs a full integrity check of the database. Can be slow.
Usage: ``PRAGMA integrity_check;``

- **quick_check** — (command, not a setting)
Faster integrity check that skips index verification.
Usage: ``PRAGMA quick_check;``

- **wal_checkpoint** — (command, not a setting)
Forces a WAL checkpoint. ``TRUNCATE`` mode also truncates the WAL file.
Usage: ``PRAGMA wal_checkpoint(TRUNCATE);``

- **vacuum** — (command, not a setting)
Rebuilds the database file, defragmenting it and reclaiming space.
Usage: ``VACUUM;``

**Database metadata**

- **application_id** — ``0`` (default)
A 32-bit signed integer stored in the database header. Applications
can set a unique ID so file(1) can identify the file type.
Persistent setting.

- **user_version** — ``0`` (default)
A 32-bit signed integer for application use, stored in the header.
Persistent setting.

- **schema_version** — (read-only)
The schema version number. Updated automatically when the schema
changes. Usage: ``PRAGMA schema_version;``

- **database_list** — (read-only)
Lists all attached databases. Usage: ``PRAGMA database_list;``

- **table_info** — (read-only, takes argument)
Returns metadata about a table's columns.
Usage: ``PRAGMA table_info(table_name);``
"""


# ============================================================
# Public API
# ============================================================

def create_async_engine_with_pool(
    database_url: Union[str, URL],
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: float = 30.0,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    pool_use_lifo: bool = True,
    pool_reset_on_return: Optional[str] = "rollback",
    connect_args: Optional[dict[str, Any]] = None,
    sqlite_pragmas: Optional[dict[str, Any]] = None,
    fix_cyrillic_ilike: bool = True,
    application_name: str = "sqldbunify",
    on_connect: Optional[ConnectionHook] = None,
    on_close: Optional[ConnectionHook] = None,
    log_connections: bool = False,
    echo: bool = False,
    echo_pool: bool = False,
    **kwargs: Any,
) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine with database-aware pool settings.

    Automatically adjusts pool parameters and connection arguments based
    on the database dialect detected in ``database_url``. Supported
    dialects: SQLite, PostgreSQL, MySQL, Oracle, MSSQL.

    Args:
        database_url: SQLAlchemy async URL. Accepts either a string
            (``"sqlite+aiosqlite:///db.sqlite3"``) or a
            :class:`sqlalchemy.engine.URL` instance.
        pool_size: Number of persistent connections in the pool.
        max_overflow: Maximum number of connections beyond ``pool_size``.
        pool_timeout: Seconds to wait for a connection from the pool.
        pool_recycle: Seconds after which a connection is recycled.
        pool_pre_ping: If True, verify connection liveness before use.
        pool_use_lifo: If True, reuse the most recently returned connection.
        pool_reset_on_return: Reset behavior on connection return
            (``"commit"``, ``"rollback"``, ``"auto"``, or ``None``).
        connect_args: Additional arguments passed to the DBAPI driver.
        sqlite_pragmas: Optional overrides for SQLite PRAGMAs. Merged over
            :data:`SQLITE_DEFAULT_PRAGMAS`. Set a key to ``None`` to disable
            a default PRAGMA, or add new keys to enable additional ones.
            Ignored for non-SQLite databases. See :data:`SQLITE_DEFAULT_PRAGMAS`
            for the full list of supported PRAGMAs and their meanings.
        fix_cyrillic_ilike: If True, override SQLite's built-in ``lower()``
            function with a Unicode-aware version so that ``ILIKE`` works
            correctly with Cyrillic and other non-ASCII text. SQLite-only.
        application_name: Application name reported to the server. Used
            by PostgreSQL (via ``server_settings``) for identification in
            ``pg_stat_activity``. Ignored by other dialects.
        on_connect: Optional callback invoked immediately after a new
            physical connection is created. Use it to attach resources
            to the connection via ``connection_record.info``. For SQLite,
            this callback runs **after** PRAGMAs are applied.
        on_close: Optional callback invoked when a connection is closed
            and removed from the pool. Use it to release resources
            attached in ``on_connect``.
        log_connections: If True, log the full lifecycle of each pooled
            connection (create, checkout, checkin, close) at DEBUG level
            via the ``sqldbunify`` logger. Each connection is assigned a
            short unique ID (stored under ``connection_record.info
            ["sqldbunify"]["connection_id"]``) to correlate log lines.
        echo: If True, log all SQL statements.
        echo_pool: If True, log pool checkouts/checkins.
        **kwargs: Extra arguments forwarded to ``create_async_engine``.

    Returns:
        ``AsyncEngine`` instance configured for the target database.

    Raises:
        DAOConfigurationError: If ``database_url`` is malformed.

    Note:
        When shutting down the application, call
        ``await dispose_engine(engine)`` (or ``await engine.dispose()``)
        to release pooled connections cleanly. Forgetting this can leave
        dangling connections and, for SQLite, stale ``-wal`` / ``-shm``
        files on disk.

    Example:
        Attaching and releasing a resource per connection::

            def on_connect(dbapi_connection, connection_record):
                info = connection_record.info.setdefault("myapp", {})
                info["session"] = MySessionResource()

            def on_close(dbapi_connection, connection_record):
                resource = connection_record.info.get("myapp", {}).pop("session", None)
                if resource is not None:
                    resource.release()

            engine = create_async_engine_with_pool(
                "postgresql+asyncpg://user:pass@host/db",
                on_connect=on_connect,
                on_close=on_close,
                log_connections=True,
            )
    """
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise DAOConfigurationError(f"Invalid database URL: {exc}") from exc

    dialect = url.get_backend_name()

    pool_kwargs: dict[str, Any] = {
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": pool_timeout,
        "pool_recycle": pool_recycle,
        "pool_pre_ping": pool_pre_ping,
        "pool_use_lifo": pool_use_lifo,
        "pool_reset_on_return": pool_reset_on_return,
    }

    connect_args = dict(connect_args) if connect_args else {}

    if dialect == "sqlite":
        _configure_sqlite(pool_kwargs, connect_args, url)
    elif dialect == "postgresql":
        _configure_postgresql(pool_kwargs, connect_args, application_name)
    elif dialect == "mysql":
        _configure_mysql(pool_kwargs, connect_args)
    elif dialect == "oracle":
        _configure_oracle(pool_kwargs, connect_args)
    elif dialect == "mssql":
        _configure_mssql(pool_kwargs, connect_args)

    engine = create_async_engine(
        url=url,
        echo=echo,
        echo_pool=echo_pool,
        connect_args=connect_args,
        **pool_kwargs,
        **kwargs,
    )

    # Register SQLite-specific setup first, so that PRAGMAs and the
    # Unicode ``lower`` override are applied *before* any user-supplied
    # ``on_connect`` hook runs.
    if dialect == "sqlite":
        merged_pragmas = _merge_sqlite_pragmas(sqlite_pragmas)
        _register_sqlite_setup(engine, merged_pragmas, fix_cyrillic_ilike)

    _register_connection_hooks(
        engine,
        on_connect=on_connect,
        on_close=on_close,
        log_connections=log_connections,
    )

    return engine


def create_session_factory(
    engine: AsyncEngine,
    *,
    expire_on_commit: bool = False,
) -> async_sessionmaker[AsyncSession]:
    """
    Create an async session factory bound to the given engine.

    Args:
        engine: ``AsyncEngine`` instance.
        expire_on_commit: If True, ORM objects are expired after commit
            and their attributes will be refreshed on next access.
            Defaults to False, which is the common choice for async apps
            where accessing an expired attribute after commit would
            trigger an implicit I/O operation.

    Returns:
        ``async_sessionmaker`` configured for the given engine.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=expire_on_commit,
    )


async def dispose_engine(engine: AsyncEngine) -> None:
    """
    Dispose of the engine and close all pooled connections.

    Convenience wrapper around ``await engine.dispose()``. Call this
    during application shutdown or in test teardown to release
    connections cleanly.

    Args:
        engine: ``AsyncEngine`` instance to dispose.
    """
    await engine.dispose()


# ============================================================
# Internal helpers
# ============================================================

# Namespace for sqldbunify data inside ``connection_record.info``.
_INFO_KEY = "sqldbunify"


def _merge_sqlite_pragmas(
    user_pragmas: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """
    Merge user-supplied PRAGMA overrides over the defaults.

    Rules:
        - ``None`` for a key disables the corresponding default.
        - Any other value overrides or adds a PRAGMA.
    """
    merged = dict(SQLITE_DEFAULT_PRAGMAS)
    if user_pragmas:
        for key, value in user_pragmas.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
    return merged


def _configure_sqlite(
    pool_kwargs: dict[str, Any],
    connect_args: dict[str, Any],
    url: URL,
) -> None:
    """Adjust pool and connection args for SQLite."""
    # In-memory SQLite requires a StaticPool: every connection to
    # ":memory:" gets its own private database, so a normal pool would
    # create multiple isolated in-memory databases instead of sharing one.
    if ":memory:" in str(url):
        pool_kwargs.clear()
        pool_kwargs["poolclass"] = StaticPool
    else:
        pool_kwargs["pool_size"] = min(pool_kwargs["pool_size"], 5)
        pool_kwargs["max_overflow"] = 0
        pool_kwargs.pop("pool_recycle", None)

    connect_args.setdefault("timeout", 30.0)


def _configure_postgresql(
    pool_kwargs: dict[str, Any],
    connect_args: dict[str, Any],
    application_name: str,
) -> None:
    """Adjust pool and connection args for PostgreSQL."""
    pool_kwargs["max_overflow"] = 10
    pool_kwargs["pool_recycle"] = 300

    connect_args.setdefault("command_timeout", 15.0)
    server_settings = connect_args.setdefault("server_settings", {})
    server_settings.setdefault("application_name", application_name)


def _configure_mysql(
    pool_kwargs: dict[str, Any], connect_args: dict[str, Any]
) -> None:
    """Adjust pool and connection args for MySQL."""
    pool_kwargs["pool_recycle"] = 300
    connect_args.setdefault("charset", "utf8mb4")


def _configure_oracle(
    pool_kwargs: dict[str, Any], connect_args: dict[str, Any]
) -> None:
    """Adjust pool and connection args for Oracle."""
    pool_kwargs["max_overflow"] = 0
    pool_kwargs["pool_recycle"] = 1800


def _configure_mssql(
    pool_kwargs: dict[str, Any], connect_args: dict[str, Any]
) -> None:
    """Adjust pool and connection args for MSSQL."""
    pool_kwargs["pool_recycle"] = 1800


def _register_sqlite_setup(
    engine: AsyncEngine,
    pragmas: dict[str, Any],
    fix_cyrillic_ilike: bool,
) -> None:
    """
    Register a ``connect`` event listener that applies SQLite PRAGMAs,
    disables extension loading, and (optionally) fixes ``lower()`` for
    non-ASCII text on each new connection.
    """
    @event.listens_for(engine.sync_engine, "connect")
    def _setup_connection(dbapi_connection: Any, _connection_record: Any) -> None:
        # Security: extensions are disabled by default via the method,
        # not via a connect() kwarg (which sqlite3 does not support).
        # Some drivers do not expose the method; skip silently.
        with contextlib.suppress(AttributeError):
            dbapi_connection.enable_load_extension(False)

        cursor = dbapi_connection.cursor()
        try:
            for key, value in pragmas.items():
                if isinstance(value, bool):
                    cursor.execute(f"PRAGMA {key} = {1 if value else 0};")
                elif isinstance(value, str):
                    cursor.execute(f"PRAGMA {key} = '{value}';")
                else:
                    cursor.execute(f"PRAGMA {key} = {value};")
        finally:
            cursor.close()

        if fix_cyrillic_ilike:
            dbapi_connection.create_function(
                "lower", 1, lambda s: s.lower() if s else s
            )


def _register_connection_hooks(
    engine: AsyncEngine,
    *,
    on_connect: Optional[ConnectionHook],
    on_close: Optional[ConnectionHook],
    log_connections: bool,
) -> None:
    """
    Register pool lifecycle listeners for logging and user hooks.

    - ``connect``:  log new connection, then call ``on_connect``.
    - ``checkout``: log when a connection leaves the pool.
    - ``checkin``:  log when a connection returns to the pool.
    - ``close``:    log when a connection is physically closed, then
        call ``on_close``.

    User hooks receive the raw ``dbapi_connection`` and the
    :class:`~sqlalchemy.pool.ConnectionPoolEntry`. Resource data can be
    stored in ``connection_record.info`` under any namespace; sqldbunify
    reserves the ``"sqldbunify"`` key for its own bookkeeping.
    """

    def _connection_id(connection_record: ConnectionPoolEntry) -> str:
        info = connection_record.info.get(_INFO_KEY)
        return info.get("connection_id", "?") if info else "?"

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect_hook(
        dbapi_connection: Any,
        connection_record: ConnectionPoolEntry,
    ) -> None:
        if log_connections:
            info = connection_record.info.setdefault(_INFO_KEY, {})
            info["connection_id"] = uuid.uuid4().hex[:8]
            logger.debug(
                "New connection [%s]", info["connection_id"]
            )

        if on_connect is not None:
            on_connect(dbapi_connection, connection_record)

    @event.listens_for(engine.sync_engine, "checkout")
    def _on_checkout_hook(
        _dbapi_connection: Any,
        connection_record: ConnectionPoolEntry,
        _connection_proxy: Any,
    ) -> None:
        if log_connections:
            logger.debug(
                "Checkout connection [%s]", _connection_id(connection_record)
            )

    @event.listens_for(engine.sync_engine, "checkin")
    def _on_checkin_hook(
        _dbapi_connection: Any,
        connection_record: ConnectionPoolEntry,
    ) -> None:
        if log_connections:
            logger.debug(
                "Checkin connection [%s]", _connection_id(connection_record)
            )

    @event.listens_for(engine.sync_engine, "close")
    def _on_close_hook(
        dbapi_connection: Any,
        connection_record: ConnectionPoolEntry,
    ) -> None:
        if log_connections:
            logger.debug(
                "Closing connection [%s]", _connection_id(connection_record)
            )

        if on_close is not None:
            on_close(dbapi_connection, connection_record)

        # Clean up our own bookkeeping data from the connection record.
        connection_record.info.pop(_INFO_KEY, None)


__all__ = [
    "ConnectionHook",
    "SQLITE_DEFAULT_PRAGMAS",
    "create_async_engine_with_pool",
    "create_session_factory",
    "dispose_engine",
]
