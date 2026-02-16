# SPDX-License-Identifier: MIT
"""Custom list CLI commands."""

from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, Protocol, TypeVar

import click

from ..cache import custom_list_manager
from ..enums import AssessmentType
from ..logging_config import get_status_logger


P = ParamSpec("P")
R = TypeVar("R")


class CliErrorDecorator(Protocol):
    """Decorator signature for CLI error handling wrappers."""

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]: ...


def register_custom_list_commands(
    main: click.Group,
    handle_cli_errors: CliErrorDecorator,
) -> None:
    """Register custom-list commands on the main CLI group."""

    @main.group(name="custom-list")
    def custom_list() -> None:
        """Manage custom journal lists."""
        pass

    @custom_list.command(name="add")
    @click.argument("file_path", type=click.Path(exists=True))
    @click.option(
        "--list-type",
        type=click.Choice(
            [
                AssessmentType.PREDATORY,
                AssessmentType.LEGITIMATE,
                AssessmentType.SUSPICIOUS,
                AssessmentType.UNKNOWN,
            ]
        ),
        default=AssessmentType.PREDATORY,
        help="Type of journals in the list",
    )
    @click.option("--list-name", required=True, help="Name for the custom list source")
    @handle_cli_errors
    def add_custom_list(file_path: str, list_type: str, list_name: str) -> None:
        """Add a custom journal list from a file.

        Args:
            file_path: Path to CSV or JSON file containing journal names.
            list_type: Type of journals in the list (predatory, legitimate, etc.).
            list_name: Name for the custom list source.
        """
        status_logger = get_status_logger()

        status_logger.info(f"Adding custom list '{list_name}' from {file_path}")
        status_logger.info(f"List type: {list_type}")

        assessment_type = AssessmentType(list_type)

        try:
            manager = custom_list_manager.CustomListManager()
            manager.add_custom_list(list_name, file_path, assessment_type)

            status_logger.info(f"Successfully added custom list '{list_name}'")
            status_logger.info("Run 'aletheia-probe sync' to load the data into cache")

        except ValueError as e:
            status_logger.error(f"Failed to add custom list: {e}")
            raise click.ClickException(str(e)) from e

    @custom_list.command(name="list")
    @handle_cli_errors
    def list_custom_lists() -> None:
        """List all registered custom journal lists."""
        status_logger = get_status_logger()

        try:
            manager = custom_list_manager.CustomListManager()
            custom_lists = manager.get_all_custom_lists()

            if not custom_lists:
                status_logger.info("No custom lists found")
                return

            status_logger.info(f"Found {len(custom_lists)} custom list(s):")
            status_logger.info("")

            for custom_list in custom_lists:
                list_name = custom_list["list_name"]
                file_path = custom_list["file_path"]
                list_type = custom_list["list_type"]
                enabled = custom_list["enabled"]
                created_at = custom_list["created_at"]

                file_exists = Path(file_path).exists()
                file_status = "✓" if file_exists else "✗ (missing)"

                status_text = f"  {list_name}:"
                status_logger.info(status_text)
                status_logger.info(f"    Type: {list_type}")
                status_logger.info(f"    File: {file_path} {file_status}")
                status_logger.info(
                    f"    Status: {'Enabled' if enabled else 'Disabled'}"
                )
                status_logger.info(f"    Created: {created_at}")
                status_logger.info("")

        except Exception as e:
            status_logger.error(f"Failed to list custom lists: {e}")
            raise click.ClickException(str(e)) from e

    @custom_list.command(name="remove")
    @click.argument("list_name")
    @click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
    @handle_cli_errors
    def remove_custom_list(list_name: str, confirm: bool) -> None:
        """Remove a custom journal list.

        Args:
            list_name: Name of the custom list to remove.
            confirm: Whether to skip the confirmation prompt.
        """
        status_logger = get_status_logger()

        try:
            manager = custom_list_manager.CustomListManager()

            if not manager.custom_list_exists(list_name):
                status_logger.error(f"Custom list '{list_name}' not found")
                raise click.ClickException(f"Custom list '{list_name}' does not exist")

            if not confirm:
                click.confirm(
                    f"Are you sure you want to remove custom list '{list_name}'?",
                    abort=True,
                )

            success = manager.remove_custom_list(list_name)

            if success:
                status_logger.info(f"Successfully removed custom list '{list_name}'")
            else:
                status_logger.error(f"Failed to remove custom list '{list_name}'")
                raise click.ClickException("Removal failed")

        except click.ClickException:
            raise
        except Exception as e:
            status_logger.error(f"Failed to remove custom list: {e}")
            raise click.ClickException(str(e)) from e
