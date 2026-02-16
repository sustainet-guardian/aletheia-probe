# SPDX-License-Identifier: MIT
"""Database maintenance CLI commands."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, Protocol, TypeVar

import click

from ..cache.migrations import migrate_database, reset_database
from ..cache.schema import SCHEMA_VERSION, get_schema_version
from ..config import get_config_manager
from ..logging_config import get_status_logger


P = ParamSpec("P")
R = TypeVar("R")


class CliErrorDecorator(Protocol):
    """Decorator signature for CLI error handling wrappers."""

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]: ...


def register_db_commands(
    main: click.Group,
    handle_cli_errors: CliErrorDecorator,
) -> None:
    """Register db commands on the main CLI group."""

    @main.group(name="db")
    def db() -> None:
        """Manage database schema and versioning."""
        pass

    @db.command(name="version")
    @handle_cli_errors
    def db_version() -> None:
        """Show the current database schema version."""
        status_logger = get_status_logger()

        db_path = Path(get_config_manager().load_config().cache.db_path)

        if not db_path.exists():
            status_logger.info(
                "Database does not exist yet (will be created on first use)"
            )
            status_logger.info(f"Expected schema version: {SCHEMA_VERSION}")
            return

        current_version = get_schema_version(db_path)

        if current_version is None:
            status_logger.warning("⚠️  Legacy database detected (no version tracking)")
            status_logger.info(
                f"Current code requires: schema version {SCHEMA_VERSION}"
            )
            status_logger.info("\nDelete the database and run sync again:")
            status_logger.info(f"  rm {db_path}")
            status_logger.info("  aletheia-probe sync")
        elif current_version < SCHEMA_VERSION:
            status_logger.warning(f"⚠️  Database schema version: {current_version}")
            status_logger.info(f"Current code requires: version {SCHEMA_VERSION}")
            status_logger.info("\nDelete the database and run sync again:")
            status_logger.info(f"  rm {db_path}")
            status_logger.info("  aletheia-probe sync")
        elif current_version > SCHEMA_VERSION:
            status_logger.error(f"❌ Database schema version: {current_version}")
            status_logger.error(
                f"Current code supports up to: version {SCHEMA_VERSION}"
            )
            status_logger.info("\nPlease upgrade aletheia-probe:")
            status_logger.info("  pip install --upgrade aletheia-probe")
        else:
            status_logger.info(f"✅ Database schema version: {current_version}")
            status_logger.info("Schema is up to date")

    @db.command(name="migrate")
    @click.option(
        "--target-version",
        type=int,
        help="Target version to migrate to (default: latest)",
    )
    @handle_cli_errors
    def db_migrate(target_version: int | None) -> None:
        """Migrate database to a newer schema version.

        Creates a backup before migration.

        Args:
            target_version: Target version to migrate to (default: latest).
        """
        status_logger = get_status_logger()

        db_path = Path(get_config_manager().load_config().cache.db_path)

        if not db_path.exists():
            status_logger.error("Database does not exist yet")
            status_logger.info("Run any command to create a new database automatically")
            sys.exit(1)

        if target_version is None:
            target_version = SCHEMA_VERSION

        try:
            success = migrate_database(db_path, target_version)
            if success:
                sys.exit(0)
            else:
                sys.exit(1)
        except Exception as e:
            status_logger.error(f"Migration failed: {e}")
            sys.exit(1)

    @db.command(name="reset")
    @click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
    @handle_cli_errors
    def db_reset(confirm: bool) -> None:
        """Reset database to current schema version.

        WARNING: This deletes all data! Creates a backup first.

        Args:
            confirm: Whether to skip the confirmation prompt.
        """
        status_logger = get_status_logger()

        db_path = Path(get_config_manager().load_config().cache.db_path)

        if not db_path.exists():
            status_logger.info("Database does not exist yet (nothing to reset)")
            return

        if not confirm:
            status_logger.warning(
                "⚠️  WARNING: This will DELETE ALL DATA in the database!"
            )
            status_logger.info("A backup will be created before deletion.")
            click.confirm("\nAre you sure you want to reset the database?", abort=True)

        try:
            success = reset_database(db_path, confirm=True)
            if success:
                sys.exit(0)
            else:
                sys.exit(1)
        except Exception as e:
            status_logger.error(f"Reset failed: {e}")
            sys.exit(1)
