# SPDX-License-Identifier: MIT
"""Shared typing and dependencies for CLI command registration."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, ParamSpec, Protocol, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


class CliErrorDecorator(Protocol):
    """Decorator signature for CLI error handling wrappers."""

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]: ...


class RunLookupCli(Protocol):
    """Lookup runner callable signature."""

    def __call__(
        self,
        publication_name: str,
        venue_type: Any,
        output_format: str,
        confidence_min: float,
        online: bool = True,
    ) -> None: ...


class AsyncAssessPublication(Protocol):
    """Publication assessment coroutine signature."""

    def __call__(
        self,
        publication_name: str,
        publication_type: str,
        verbose: bool,
        output_format: str,
        *,
        use_acronyms: bool,
        confidence_min: float,
    ) -> Coroutine[Any, Any, None]: ...


class AsyncMassEvalMain(Protocol):
    """Mass evaluation coroutine signature."""

    def __call__(
        self,
        input_path: str,
        mode: str,
        output_dir: str | None,
        state_file: str,
        resume: bool,
        relax_bibtex: bool,
        retry_forever: bool,
        max_concurrency: int,
        checkpoint_interval_seconds: int = ...,
        collect_cache_file: str | None = ...,
        cache_ttl_hours: int = ...,
        max_parallel_files: int = ...,
    ) -> Coroutine[Any, Any, None]: ...


@dataclass(frozen=True)
class CoreCommandContext:
    """Dependency container for core command module registration."""

    handle_cli_errors: CliErrorDecorator
    default_acronym_confidence_min: float
    large_sync_backends: frozenset[str]
    github_http_timeout_seconds: int
    github_allowed_hosts: set[str]
    get_cache_sync_manager_fn: Callable[[], Any]
    run_async: Callable[[Coroutine[Any, Any, Any]], Any]
    get_config_manager_fn: Callable[..., Any]
    get_backend_registry_fn: Callable[[], Any]
    auto_register_custom_lists_fn: Callable[[], None]
    create_acronym_cache: Callable[[], Any]
    create_assessment_cache: Callable[[], Any]
    create_openalex_cache: Callable[[], Any]
    create_retraction_cache: Callable[[], Any]
    async_assess_publication: AsyncAssessPublication
    run_lookup_cli: RunLookupCli
    async_bibtex_main: Callable[[str, bool, str, bool], Coroutine[Any, Any, None]]
    async_mass_eval_main: AsyncMassEvalMain
    get_latest_acronym_dataset_url: Callable[[str], tuple[str, str]]
    fetch_https_json: Callable[
        [str, int, set[str]], Coroutine[Any, Any, dict[str, Any] | list[Any]]
    ]
