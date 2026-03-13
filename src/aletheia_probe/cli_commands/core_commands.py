# SPDX-License-Identifier: MIT
"""Core CLI command orchestration and registration."""

from collections.abc import Callable, Coroutine
from typing import Any

import click

from .acronym_commands import register_acronym_commands
from .assessment_commands import register_assessment_commands
from .context import (
    AsyncAssessPublication,
    AsyncMassEvalMain,
    CliErrorDecorator,
    CoreCommandContext,
    RunLookupCli,
)
from .lookup_commands import register_lookup_commands
from .retraction_cache_commands import register_retraction_cache_commands
from .system_commands import register_system_commands


def register_core_commands(
    main: click.Group,
    handle_cli_errors: CliErrorDecorator,
    default_acronym_confidence_min: float,
    large_sync_backends: frozenset[str],
    github_http_timeout_seconds: int,
    github_allowed_hosts: set[str],
    get_cache_sync_manager_fn: Callable[[], Any],
    run_async: Callable[[Coroutine[Any, Any, Any]], Any],
    get_config_manager_fn: Callable[..., Any],
    get_backend_registry_fn: Callable[[], Any],
    auto_register_custom_lists_fn: Callable[[], None],
    create_acronym_cache: Callable[[], Any],
    create_assessment_cache: Callable[[], Any],
    create_openalex_cache: Callable[[], Any],
    create_retraction_cache: Callable[[], Any],
    async_assess_publication: AsyncAssessPublication,
    run_lookup_cli: RunLookupCli,
    async_bibtex_main: Callable[[str, bool, str, bool], Coroutine[Any, Any, None]],
    async_mass_eval_main: AsyncMassEvalMain,
    get_latest_acronym_dataset_url: Callable[[str], tuple[str, str]],
    fetch_https_json: Callable[
        [str, int, set[str]], Coroutine[Any, Any, dict[str, Any] | list[Any]]
    ],
) -> None:
    """Register core command groups and commands."""
    context = CoreCommandContext(
        handle_cli_errors=handle_cli_errors,
        default_acronym_confidence_min=default_acronym_confidence_min,
        large_sync_backends=large_sync_backends,
        github_http_timeout_seconds=github_http_timeout_seconds,
        github_allowed_hosts=github_allowed_hosts,
        get_cache_sync_manager_fn=get_cache_sync_manager_fn,
        run_async=run_async,
        get_config_manager_fn=get_config_manager_fn,
        get_backend_registry_fn=get_backend_registry_fn,
        auto_register_custom_lists_fn=auto_register_custom_lists_fn,
        create_acronym_cache=create_acronym_cache,
        create_assessment_cache=create_assessment_cache,
        create_openalex_cache=create_openalex_cache,
        create_retraction_cache=create_retraction_cache,
        async_assess_publication=async_assess_publication,
        run_lookup_cli=run_lookup_cli,
        async_bibtex_main=async_bibtex_main,
        async_mass_eval_main=async_mass_eval_main,
        get_latest_acronym_dataset_url=get_latest_acronym_dataset_url,
        fetch_https_json=fetch_https_json,
    )

    register_assessment_commands(main, context)
    register_lookup_commands(main, context)
    register_system_commands(main, context)
    register_acronym_commands(main, context)
    register_retraction_cache_commands(main, context)


__all__ = ["register_core_commands"]
