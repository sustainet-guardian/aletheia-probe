# SPDX-License-Identifier: MIT
"""Command-line interface for the journal assessment tool."""

import asyncio
import sys
from pathlib import Path

import click

from . import __version__
from .backends import base as backend_base
from .cache import (
    AcronymCache,
    AssessmentCache,
    OpenAlexCache,
    RetractionCache,
    custom_list_manager,
)
from .cache.schema import SchemaVersionError
from .cli_commands.core_commands import register_core_commands
from .cli_commands.custom_list import register_custom_list_commands
from .cli_commands.db import register_db_commands
from .cli_logic.assessment import _async_assess_publication, _async_bibtex_main
from .cli_logic.error_handling import handle_cli_errors
from .cli_logic.lookup import _run_lookup_cli
from .cli_logic.mass_eval import _async_mass_eval_main
from .cli_logic.network import (
    GITHUB_ALLOWED_HOSTS,
    GITHUB_HTTP_TIMEOUT_SECONDS,
    _fetch_https_json,
    _get_latest_acronym_dataset_url,
)
from .config import get_config_manager
from .constants import DEFAULT_ACRONYM_CONFIDENCE_MIN
from .logging_config import get_status_logger, setup_logging


LARGE_SYNC_BACKENDS: frozenset[str] = frozenset({"dblp_venues"})


# Import cache_sync last: instantiation at module level may raise SchemaVersionError
# if the database schema is outdated. Caught here for a clean error message.
_startup_error: SchemaVersionError | None = None
try:
    from .cache_sync import cache_sync_manager  # noqa: E402
except SchemaVersionError as _e:
    _startup_error = _e
    cache_sync_manager = None


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print version and exit if requested."""
    if value:
        setup_logging()
        status_logger = get_status_logger()
        status_logger.info(f"Aletheia-Probe version {__version__}")
        ctx.exit(0)


@click.group()
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show version information and exit",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.pass_context
def main(ctx: click.Context, config: Path | None) -> None:
    """Aletheia-Probe - Assess whether journals are predatory or legitimate."""
    del ctx
    detail_logger, status_logger = setup_logging()
    detail_logger.debug("CLI initialized")

    if _startup_error is not None:
        status_logger.error(str(_startup_error))
        sys.exit(1)

    if config:
        detail_logger.debug(f"Using config file: {config}")
        get_config_manager(config, force_reload=True)


register_core_commands(
    main=main,
    handle_cli_errors=handle_cli_errors,
    default_acronym_confidence_min=DEFAULT_ACRONYM_CONFIDENCE_MIN,
    large_sync_backends=LARGE_SYNC_BACKENDS,
    github_http_timeout_seconds=GITHUB_HTTP_TIMEOUT_SECONDS,
    github_allowed_hosts=GITHUB_ALLOWED_HOSTS,
    get_cache_sync_manager_fn=lambda: cache_sync_manager,
    run_async=lambda coro: asyncio.run(coro),
    get_config_manager_fn=lambda *args, **kwargs: get_config_manager(*args, **kwargs),
    get_backend_registry_fn=lambda: backend_base.get_backend_registry(),
    auto_register_custom_lists_fn=lambda: (
        custom_list_manager.auto_register_custom_lists()
    ),
    create_acronym_cache=lambda: AcronymCache(),
    create_assessment_cache=lambda: AssessmentCache(),
    create_openalex_cache=lambda: OpenAlexCache(),
    create_retraction_cache=lambda: RetractionCache(),
    async_assess_publication=lambda *args, **kwargs: _async_assess_publication(
        *args, **kwargs
    ),
    run_lookup_cli=lambda *args, **kwargs: _run_lookup_cli(*args, **kwargs),
    async_bibtex_main=lambda *args, **kwargs: _async_bibtex_main(*args, **kwargs),
    async_mass_eval_main=lambda *args, **kwargs: _async_mass_eval_main(*args, **kwargs),
    get_latest_acronym_dataset_url=lambda repo: _get_latest_acronym_dataset_url(repo),
    fetch_https_json=lambda *args, **kwargs: _fetch_https_json(*args, **kwargs),
)
register_custom_list_commands(main, handle_cli_errors)
register_db_commands(main, handle_cli_errors)


if __name__ == "__main__":
    main()
