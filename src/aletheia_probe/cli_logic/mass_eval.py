# SPDX-License-Identifier: MIT
"""Massive BibTeX evaluation workflow with resume/checkpoint support."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..bibtex_parser import BibtexParser
from ..cache import AcronymCache
from ..dispatcher import query_dispatcher
from ..enums import AssessmentType
from ..logging_config import get_detail_logger, get_status_logger
from ..models import AssessmentResult, BackendStatus, QueryInput
from ..normalizer import input_normalizer
from .error_handling import handle_cli_exception


STATE_VERSION = 2
CHECKPOINT_INTERVAL_SECONDS = 120
RETRY_INITIAL_SECONDS = 15.0
RETRY_MAX_SECONDS = 600.0
DEFAULT_MAX_CONCURRENCY = 1
COLLECT_CACHE_FLUSH_BATCH_SIZE = 2000
COLLECT_CACHE_FLUSH_INTERVAL_SECONDS = 30


class CollectDedupeCache:
    """Process-level dedupe cache for mass-eval collect mode."""

    def __init__(
        self,
        cache_path: Path | None,
        status_logger: Any,
        detail_logger: Any,
    ) -> None:
        self.cache_path = cache_path
        self.status_logger = status_logger
        self.detail_logger = detail_logger
        self._seen_keys: set[str] = set()
        self._pending_keys: list[str] = []
        self._inflight: dict[str, asyncio.Future[None]] = {}
        self._lock = asyncio.Lock()
        self._last_flush_time = time.time()
        self.cache_accesses: int = 0
        self.cache_hits_seen: int = 0
        self.cache_hits_wait: int = 0
        self.cache_miss_claims: int = 0
        self.cache_flushes: int = 0

    @classmethod
    async def load(
        cls,
        cache_path: Path | None,
        status_logger: Any,
        detail_logger: Any,
    ) -> CollectDedupeCache:
        """Create cache and load persisted keys from disk when available."""
        cache = cls(
            cache_path=cache_path,
            status_logger=status_logger,
            detail_logger=detail_logger,
        )
        if cache_path is None or not cache_path.exists():
            return cache

        loaded_count = 0
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                key = line.strip()
                if key:
                    cache._seen_keys.add(key)
                    loaded_count += 1

        status_logger.info(
            f"Loaded {loaded_count:,} collect dedupe keys from {cache_path}"
        )
        return cache

    async def claim_or_wait(self, key: str) -> tuple[bool, asyncio.Future[None] | None]:
        """Claim ownership for processing key, or return existing inflight future.

        Returns:
            (is_owner, future)
            - is_owner=False, future=None: key already in seen cache (skip)
            - is_owner=False, future=<Future>: wait on in-flight owner
            - is_owner=True,  future=<Future>: caller is owner and must complete key
        """
        async with self._lock:
            self.cache_accesses += 1
            if key in self._seen_keys:
                self.cache_hits_seen += 1
                return False, None

            if key in self._inflight:
                self.cache_hits_wait += 1
                return False, self._inflight[key]

            owner_future: asyncio.Future[None] = (
                asyncio.get_running_loop().create_future()
            )
            self._inflight[key] = owner_future
            self.cache_miss_claims += 1
            return True, owner_future

    async def mark_success(self, key: str, owner_future: asyncio.Future[None]) -> None:
        """Mark key processed successfully and flush pending persisted keys as needed."""
        async with self._lock:
            self._inflight.pop(key, None)
            self._seen_keys.add(key)
            self._pending_keys.append(key)
            if not owner_future.done():
                owner_future.set_result(None)

            should_flush = (
                len(self._pending_keys) >= COLLECT_CACHE_FLUSH_BATCH_SIZE
                or (time.time() - self._last_flush_time)
                >= COLLECT_CACHE_FLUSH_INTERVAL_SECONDS
            )
            if should_flush:
                self._flush_pending_locked()

    async def mark_failure(
        self, key: str, owner_future: asyncio.Future[None], error: Exception
    ) -> None:
        """Release in-flight key and propagate owner failure to waiters."""
        async with self._lock:
            self._inflight.pop(key, None)
            if not owner_future.done():
                owner_future.set_exception(error)

    async def flush(self, force: bool = False) -> None:
        """Flush pending keys to disk."""
        async with self._lock:
            if not force and len(self._pending_keys) < COLLECT_CACHE_FLUSH_BATCH_SIZE:
                if (
                    time.time() - self._last_flush_time
                ) < COLLECT_CACHE_FLUSH_INTERVAL_SECONDS:
                    return
            self._flush_pending_locked()

    def _flush_pending_locked(self) -> None:
        """Flush pending keys to disk (lock must be held)."""
        if not self._pending_keys or self.cache_path is None:
            self._last_flush_time = time.time()
            return

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "a", encoding="utf-8") as f:
            f.write("\n".join(self._pending_keys))
            f.write("\n")

        flushed = len(self._pending_keys)
        self._pending_keys.clear()
        self._last_flush_time = time.time()
        self.cache_flushes += 1
        self.detail_logger.debug(
            f"Flushed {flushed:,} collect dedupe keys to {self.cache_path}"
        )

    async def snapshot(self) -> dict[str, int]:
        """Return cache statistics for status reporting."""
        async with self._lock:
            return {
                "seen_keys": len(self._seen_keys),
                "pending_keys": len(self._pending_keys),
                "inflight_keys": len(self._inflight),
                "accesses": self.cache_accesses,
                "hits_seen": self.cache_hits_seen,
                "hits_wait": self.cache_hits_wait,
                "miss_claims": self.cache_miss_claims,
                "flushes": self.cache_flushes,
            }


class MassEvalState:
    """Simple file-backed checkpoint state for long-running mass evaluation."""

    def __init__(self, state_path: Path, mode: str, input_path: Path):
        self.state_path = state_path
        self.mode = mode
        self.input_path = str(input_path)
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.started_at
        self.completed_files: list[str] = []
        self.failed_files: dict[str, str] = {}
        self.file_progress: dict[str, dict[str, Any]] = {}
        self.current_file: str | None = None
        self.processed_entries: int = 0
        self.written_records: int = 0
        self.retry_count: int = 0
        self.collect_cache_hits: int = 0
        # Runtime-only: not persisted to disk
        self._last_checkpoint_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary."""
        return {
            "version": STATE_VERSION,
            "mode": self.mode,
            "input_path": self.input_path,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_files": self.completed_files,
            "failed_files": self.failed_files,
            "file_progress": self.file_progress,
            "current_file": self.current_file,
            "processed_entries": self.processed_entries,
            "written_records": self.written_records,
            "retry_count": self.retry_count,
            "collect_cache_hits": self.collect_cache_hits,
        }

    @classmethod
    def from_dict(cls, state_path: Path, data: dict[str, Any]) -> MassEvalState:
        """Restore state from serialized dictionary."""
        mode = str(data.get("mode", "assess"))
        input_path = Path(str(data.get("input_path", "")))
        state = cls(state_path=state_path, mode=mode, input_path=input_path)
        state.started_at = str(data.get("started_at", state.started_at))
        state.updated_at = str(data.get("updated_at", state.updated_at))
        state.completed_files = list(data.get("completed_files", []))
        state.failed_files = dict(data.get("failed_files", {}))
        state.file_progress = dict(data.get("file_progress", {}))
        current_file = data.get("current_file")
        state.current_file = str(current_file) if current_file else None
        state.processed_entries = int(data.get("processed_entries", 0))
        state.written_records = int(data.get("written_records", 0))
        state.retry_count = int(data.get("retry_count", 0))
        state.collect_cache_hits = int(data.get("collect_cache_hits", 0))
        return state


def _build_collect_cache_key_raw(venue_name: str, venue_type: Any) -> str:
    """Build stable collect dedupe key from raw venue text."""
    compact_name = " ".join(venue_name.strip().casefold().split())
    venue_type_value = getattr(venue_type, "value", str(venue_type)).strip().lower()
    payload = f"{venue_type_value}::{compact_name}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _utc_now() -> str:
    """Return UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_state(state: MassEvalState, *, force: bool = False) -> None:
    """Persist checkpoint state atomically.

    Throttled to CHECKPOINT_INTERVAL_SECONDS to avoid writing on every entry.
    Use force=True at structural boundaries (file completion, retries, end-of-run).
    """
    now = time.monotonic()
    if not force and (now - state._last_checkpoint_time) < CHECKPOINT_INTERVAL_SECONDS:
        return
    state.updated_at = _utc_now()
    payload = state.to_dict()
    tmp_path = state.state_path.with_suffix(state.state_path.suffix + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(state.state_path)
    state._last_checkpoint_time = now


def _load_or_init_state(
    state_path: Path,
    mode: str,
    input_path: Path,
    resume: bool,
    status_logger: Any,
) -> MassEvalState:
    """Load state from disk or create a fresh state."""
    if resume and state_path.exists():
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)

        if int(data.get("version", -1)) != STATE_VERSION:
            raise ValueError(
                f"Unsupported state version in {state_path}: {data.get('version')}"
            )

        state = MassEvalState.from_dict(state_path, data)
        if state.mode != mode:
            raise ValueError(
                f"State mode mismatch: requested '{mode}', state has '{state.mode}'"
            )
        if Path(state.input_path) != input_path:
            raise ValueError(
                "State input_path mismatch: requested "
                f"'{input_path}', state has '{state.input_path}'"
            )

        status_logger.info(
            f"Resuming mass-eval from checkpoint: {state_path} "
            f"({len(state.completed_files)} completed files)"
        )
        return state

    state = MassEvalState(state_path=state_path, mode=mode, input_path=input_path)
    _checkpoint_state(state, force=True)
    return state


def _discover_bib_files(input_path: Path) -> list[Path]:
    """Discover BibTeX files from a single file or recursively from a directory."""
    if input_path.is_file():
        if input_path.suffix.lower() != ".bib":
            raise ValueError(f"Input file must end with .bib: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise ValueError(f"Input path must be a .bib file or directory: {input_path}")

    files = sorted(path for path in input_path.rglob("*.bib") if path.is_file())
    if not files:
        raise ValueError(f"No .bib files found under {input_path}")
    return files


def _build_minimal_record(
    file_path: Path,
    entry: Any,
) -> dict[str, Any]:
    """Build minimal output record for a non-assessed entry (preprint, no_venue, etc.)."""
    return {
        "record_id": _record_id_for_entry(file_path, entry),
        "timestamp": _utc_now(),
        "file_path": str(file_path),
        "entry_key": entry.key,
        "venue_raw": entry.journal_name,
        "venue_type": entry.venue_type.value,
        "issn": entry.issn,
        "eissn": getattr(entry, "eissn", None),
        "doi": entry.doi,
        "state": entry.state,
        "state_reason": entry.state_reason,
        "final_assessment": None,
        "confidence": None,
        "overall_score": None,
        "is_suspicious": None,
        "has_conflict": None,
        "predatory_votes": None,
        "legitimate_votes": None,
        "predatory_list_hits": [],
        "backend_results": [],
        "reasoning": None,
    }


def _build_assess_record(
    file_path: Path,
    entry: Any,
    assessment: AssessmentResult,
) -> dict[str, Any]:
    """Build output record for one entry assessment."""
    backend_results = assessment.backend_results
    predatory_votes = sum(
        1
        for result in backend_results
        if result.status == BackendStatus.FOUND
        and result.assessment == AssessmentType.PREDATORY
    )
    legitimate_votes = sum(
        1
        for result in backend_results
        if result.status == BackendStatus.FOUND
        and result.assessment == AssessmentType.LEGITIMATE
    )

    has_conflict = predatory_votes > 0 and legitimate_votes > 0

    predatory_list_hits = [
        result.backend_name
        for result in backend_results
        if result.status == BackendStatus.FOUND
        and result.assessment == AssessmentType.PREDATORY
        and result.evidence_type == "predatory_list"
    ]

    return {
        "record_id": _record_id_for_entry(file_path, entry),
        "timestamp": _utc_now(),
        "file_path": str(file_path),
        "entry_key": entry.key,
        "venue_raw": entry.journal_name,
        "venue_type": entry.venue_type.value,
        "issn": entry.issn,
        "eissn": getattr(entry, "eissn", None),
        "doi": entry.doi,
        "state": "assessed",
        "state_reason": None,
        "final_assessment": assessment.assessment.value,
        "confidence": assessment.confidence,
        "overall_score": assessment.overall_score,
        "is_suspicious": assessment.assessment == AssessmentType.SUSPICIOUS,
        "has_conflict": has_conflict,
        "predatory_votes": predatory_votes,
        "legitimate_votes": legitimate_votes,
        "predatory_list_hits": predatory_list_hits,
        "backend_results": [result.model_dump() for result in backend_results],
        "reasoning": assessment.reasoning,
    }


def _record_id_for_entry(file_path: Path, entry: Any) -> str:
    """Build deterministic record identifier for JSONL idempotency."""
    return f"{file_path}::{entry.key}::{entry.journal_name}"


def _advance_file_progress(
    progress: dict[str, Any],
    completed_indices: set[int],
    total_entries: int,
) -> None:
    """Advance contiguous completion pointer and persist sparse completion state."""
    next_index = int(progress.get("next_entry_index", 0))
    while next_index < total_entries and next_index in completed_indices:
        completed_indices.remove(next_index)
        next_index += 1

    progress["next_entry_index"] = next_index
    progress["completed_entry_indices"] = sorted(completed_indices)


async def _assess_with_retry(
    venue_name: str,
    venue_type: Any,
    retry_forever: bool,
    state: MassEvalState,
    detail_logger: Any,
    status_logger: Any,
    on_retry: Callable[[], Awaitable[int]] | None = None,
) -> AssessmentResult:
    """Assess one venue with optional retry-forever mode on transient backend failures."""
    retry_delay = RETRY_INITIAL_SECONDS
    query_input = input_normalizer.normalize(venue_name)
    query_input.venue_type = venue_type

    while True:
        result = await query_dispatcher.assess_journal(query_input)

        if not retry_forever:
            return result

        transient_statuses = {BackendStatus.RATE_LIMITED, BackendStatus.TIMEOUT}
        transient_backends = [
            f"{backend_result.backend_name}:{backend_result.status.value}"
            for backend_result in result.backend_results
            if backend_result.status in transient_statuses
        ]
        if not transient_backends:
            return result

        if on_retry is not None:
            attempt_number = await on_retry()
        else:
            state.retry_count += 1
            _checkpoint_state(state, force=True)
            attempt_number = state.retry_count

        sleep_seconds = min(retry_delay, RETRY_MAX_SECONDS)
        jitter = random.uniform(0.0, sleep_seconds * 0.2)
        wait_seconds = sleep_seconds + jitter

        status_logger.warning(
            f"Transient backend statuses encountered for '{venue_name}'. "
            f"Backends={transient_backends}. "
            f"Retrying in {wait_seconds:.1f}s (attempt #{attempt_number})."
        )
        detail_logger.debug(
            f"Retry details: base_delay={retry_delay:.1f}, jitter={jitter:.1f}, wait={wait_seconds:.1f}"
        )

        await _sleep(wait_seconds)
        retry_delay = min(RETRY_MAX_SECONDS, retry_delay * 2)


async def _collect_with_retry(
    venue_name: str,
    venue_type: Any,
    retry_forever: bool,
    state: MassEvalState,
    detail_logger: Any,
    status_logger: Any,
    on_retry: Callable[[], Awaitable[int]] | None = None,
    prepared_query_input: QueryInput | None = None,
) -> None:
    """Warm normalization/identifier caches without running assessments."""
    retry_delay = RETRY_INITIAL_SECONDS
    acronym_cache = AcronymCache()
    first_attempt = True

    while True:
        try:
            if first_attempt and prepared_query_input is not None:
                query_input = prepared_query_input
            else:
                query_input = input_normalizer.normalize(venue_name)
                query_input.venue_type = venue_type

            (
                normalization,
                failure_reason,
            ) = await query_dispatcher._normalize_for_dispatch(query_input)
            query_input = query_dispatcher._attach_normalization_to_query(
                query_input, normalization
            )
            query_input = await query_dispatcher._enrich_query_identifiers(query_input)

            # Persist acronym mappings discovered during normalization.
            for acronym, full_name in query_input.extracted_acronym_mappings.items():
                acronym_cache.store_acronym_mapping(
                    acronym,
                    full_name,
                    query_input.venue_type.value,
                    source="mass_eval_collect",
                )

            # Collect mode is best-effort cache warm-up; normalization misses are
            # recorded as detail diagnostics but do not fail processing.
            if failure_reason:
                detail_logger.debug(
                    f"Collect mode normalization note for '{venue_name}': {failure_reason}"
                )
            return

        except Exception as e:
            first_attempt = False
            if not retry_forever:
                raise

            if on_retry is not None:
                attempt_number = await on_retry()
            else:
                state.retry_count += 1
                _checkpoint_state(state, force=True)
                attempt_number = state.retry_count

            sleep_seconds = min(retry_delay, RETRY_MAX_SECONDS)
            jitter = random.uniform(0.0, sleep_seconds * 0.2)
            wait_seconds = sleep_seconds + jitter

            status_logger.warning(
                f"Collect mode transient failure for '{venue_name}': {e}. "
                f"Retrying in {wait_seconds:.1f}s (attempt #{attempt_number})."
            )
            detail_logger.debug(
                f"Collect retry details: base_delay={retry_delay:.1f}, "
                f"jitter={jitter:.1f}, wait={wait_seconds:.1f}"
            )

            await _sleep(wait_seconds)
            retry_delay = min(RETRY_MAX_SECONDS, retry_delay * 2)


async def _sleep(seconds: float) -> None:
    """Async sleep wrapper to keep this module easy to test."""
    import asyncio

    await asyncio.sleep(seconds)


def _append_jsonl_record(output_file: Path, record: dict[str, Any]) -> None:
    """Append a single JSON record as one line."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_existing_record_ids(output_file: Path) -> set[str]:
    """Load existing record IDs from JSONL file for duplicate suppression."""
    if not output_file.exists():
        return set()

    record_ids: set[str] = set()
    with open(output_file, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            record_id = payload.get("record_id")
            if isinstance(record_id, str) and record_id:
                record_ids.add(record_id)
    return record_ids


async def _process_single_file(
    file_path: Path,
    input_root: Path,
    mode: str,
    retry_forever: bool,
    relax_bibtex: bool,
    output_dir: Path | None,
    max_concurrency: int,
    state: MassEvalState,
    detail_logger: Any,
    status_logger: Any,
    collect_dedupe_cache: CollectDedupeCache | None = None,
) -> None:
    """Process one .bib file with entry-level checkpointing and resume."""
    processed_before = state.processed_entries
    written_before = state.written_records
    collect_hits_before = state.collect_cache_hits

    try:
        entries = BibtexParser.parse_bibtex_file_all(
            file_path,
            relax_parsing=relax_bibtex,
        )
    except ValueError as parse_error:
        if relax_bibtex:
            raise

        status_logger.warning(
            f"Strict BibTeX parse failed for {file_path}. "
            "Retrying with relaxed parser mode."
        )
        detail_logger.warning(
            f"Strict parse error for {file_path}: {parse_error}. "
            "Retrying with relax_parsing=True."
        )
        entries = BibtexParser.parse_bibtex_file_all(
            file_path,
            relax_parsing=True,
        )

    async def _log_file_completion(summary_status: str) -> None:
        """Emit one status-log line with file and cache statistics."""
        file_processed_entries = state.processed_entries - processed_before
        file_written_records = state.written_records - written_before
        file_collect_hits = state.collect_cache_hits - collect_hits_before
        message = (
            f"File completed: status={summary_status}, file={file_path}, "
            f"entries_total={len(entries)}, entries_processed={file_processed_entries}, "
            f"records_written={file_written_records}, "
            f"collect_cache_hits={file_collect_hits}"
        )
        if collect_dedupe_cache is None:
            status_logger.info(message)
            return

        cache_stats = await collect_dedupe_cache.snapshot()
        status_logger.info(
            f"{message}, "
            f"collect_cache_seen_keys={cache_stats['seen_keys']}, "
            f"collect_cache_accesses={cache_stats['accesses']}, "
            f"collect_cache_hit_seen={cache_stats['hits_seen']}, "
            f"collect_cache_hit_wait={cache_stats['hits_wait']}, "
            f"collect_cache_miss_claims={cache_stats['miss_claims']}, "
            f"collect_cache_inflight={cache_stats['inflight_keys']}, "
            f"collect_cache_pending_flush={cache_stats['pending_keys']}, "
            f"collect_cache_flushes={cache_stats['flushes']}"
        )

    file_key = str(file_path)
    progress = state.file_progress.setdefault(
        file_key,
        {
            "next_entry_index": 0,
            "completed_entry_indices": [],
            "written_records": 0,
            "last_error": None,
        },
    )
    next_entry_index = int(progress.get("next_entry_index", 0))
    completed_entry_indices = {
        int(index)
        for index in progress.get("completed_entry_indices", [])
        if isinstance(index, int) and index >= next_entry_index
    }

    output_file: Path | None = None
    existing_record_ids: set[str] = set()
    if mode == "assess" and output_dir is not None:
        if input_root.is_dir():
            relative_base = file_path.relative_to(input_root)
            relative_jsonl = (
                "__".join(relative_base.parts).replace(".bib", "") + ".jsonl"
            )
        else:
            relative_jsonl = file_path.stem + ".jsonl"
        output_file = output_dir / relative_jsonl
        existing_record_ids = _load_existing_record_ids(output_file)

    if next_entry_index >= len(entries):
        status_logger.info(
            f"File already complete by checkpoint: {file_path} (entries={len(entries)})"
        )
        if file_key not in state.completed_files:
            state.completed_files.append(file_key)
        state.failed_files.pop(file_key, None)
        progress["completed_entry_indices"] = []
        progress["last_error"] = None
        _checkpoint_state(state, force=True)
        await _log_file_completion("already_complete")
        return

    pending_indices = [
        index
        for index in range(next_entry_index, len(entries))
        if index not in completed_entry_indices
    ]
    if not pending_indices:
        _advance_file_progress(progress, completed_entry_indices, len(entries))
        if file_key not in state.completed_files:
            state.completed_files.append(file_key)
        state.failed_files.pop(file_key, None)
        progress["last_error"] = None
        _checkpoint_state(state, force=True)
        await _log_file_completion("already_complete_sparse")
        return

    workers = max(1, min(max_concurrency, len(pending_indices)))
    index_queue: asyncio.Queue[int] = asyncio.Queue()
    for index in pending_indices:
        index_queue.put_nowait(index)

    state_lock = asyncio.Lock()

    async def _reserve_retry_attempt() -> int:
        async with state_lock:
            state.retry_count += 1
            _checkpoint_state(state, force=True)
            return state.retry_count

    async def _process_entry(entry_index: int) -> None:
        entry = entries[entry_index]
        detail_logger.debug(
            f"Processing entry {entry_index + 1}/{len(entries)} in {file_path}: "
            f"key={entry.key}, venue_type={entry.venue_type.value}, state={entry.state}"
        )

        if entry.state != "assessed":
            # Non-assessed entry: skip backend calls, write minimal record in assess mode
            if mode == "assess":
                if output_file is None:
                    raise ValueError("Output file is not configured in assess mode")
                record = _build_minimal_record(file_path, entry)
                record_id = str(record["record_id"])
                async with state_lock:
                    if record_id not in existing_record_ids:
                        _append_jsonl_record(output_file, record)
                        existing_record_ids.add(record_id)
                        state.written_records += 1
                        progress["written_records"] = (
                            int(progress.get("written_records", 0)) + 1
                        )
                    state.processed_entries += 1
                    completed_entry_indices.add(entry_index)
                    _advance_file_progress(
                        progress, completed_entry_indices, len(entries)
                    )
                    progress["last_error"] = None
                    _checkpoint_state(state)
            else:
                # collect mode: nothing to cache for non-assessed entry
                async with state_lock:
                    state.processed_entries += 1
                    completed_entry_indices.add(entry_index)
                    _advance_file_progress(
                        progress, completed_entry_indices, len(entries)
                    )
                    progress["last_error"] = None
                    _checkpoint_state(state)
            return

        if mode == "collect":
            collect_cache_key = _build_collect_cache_key_raw(
                entry.journal_name,
                entry.venue_type,
            )

            if collect_dedupe_cache is not None:
                is_owner, wait_future = await collect_dedupe_cache.claim_or_wait(
                    collect_cache_key
                )
                if not is_owner:
                    if wait_future is not None:
                        await wait_future
                    async with state_lock:
                        state.collect_cache_hits += 1
                        state.processed_entries += 1
                        completed_entry_indices.add(entry_index)
                        _advance_file_progress(
                            progress, completed_entry_indices, len(entries)
                        )
                        progress["last_error"] = None
                        _checkpoint_state(state)
                    return

                if wait_future is None:
                    raise ValueError("Collect dedupe cache owner future is missing")

                try:
                    prepared_query_input = input_normalizer.normalize(
                        entry.journal_name
                    )
                    prepared_query_input.venue_type = entry.venue_type
                    await _collect_with_retry(
                        venue_name=entry.journal_name,
                        venue_type=entry.venue_type,
                        retry_forever=retry_forever,
                        state=state,
                        detail_logger=detail_logger,
                        status_logger=status_logger,
                        on_retry=_reserve_retry_attempt,
                        prepared_query_input=prepared_query_input,
                    )
                    await collect_dedupe_cache.mark_success(
                        collect_cache_key, wait_future
                    )
                except Exception as e:
                    await collect_dedupe_cache.mark_failure(
                        collect_cache_key, wait_future, e
                    )
                    raise
            else:
                prepared_query_input = input_normalizer.normalize(entry.journal_name)
                prepared_query_input.venue_type = entry.venue_type
                await _collect_with_retry(
                    venue_name=entry.journal_name,
                    venue_type=entry.venue_type,
                    retry_forever=retry_forever,
                    state=state,
                    detail_logger=detail_logger,
                    status_logger=status_logger,
                    on_retry=_reserve_retry_attempt,
                    prepared_query_input=prepared_query_input,
                )

            async with state_lock:
                state.processed_entries += 1
                completed_entry_indices.add(entry_index)
                _advance_file_progress(progress, completed_entry_indices, len(entries))
                progress["last_error"] = None
                _checkpoint_state(state)
        else:
            assessment = await _assess_with_retry(
                venue_name=entry.journal_name,
                venue_type=entry.venue_type,
                retry_forever=retry_forever,
                state=state,
                detail_logger=detail_logger,
                status_logger=status_logger,
                on_retry=_reserve_retry_attempt,
            )
            if output_file is None:
                raise ValueError("Output file is not configured in assess mode")
            record = _build_assess_record(file_path, entry, assessment)
            record_id = str(record["record_id"])

            async with state_lock:
                if record_id not in existing_record_ids:
                    _append_jsonl_record(output_file, record)
                    existing_record_ids.add(record_id)
                    state.written_records += 1
                    progress["written_records"] = (
                        int(progress.get("written_records", 0)) + 1
                    )

                state.processed_entries += 1
                completed_entry_indices.add(entry_index)
                _advance_file_progress(progress, completed_entry_indices, len(entries))
                progress["last_error"] = None
                _checkpoint_state(state)

    async def _worker() -> None:
        while True:
            try:
                entry_index = index_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                await _process_entry(entry_index)
            except Exception:
                raise
            finally:
                index_queue.task_done()

    status_logger.info(
        f"Processing file with {workers} worker(s): {file_path} "
        f"(pending entries: {len(pending_indices)})"
    )
    tasks = [asyncio.create_task(_worker()) for _ in range(workers)]
    try:
        await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    if file_key not in state.completed_files:
        state.completed_files.append(file_key)
    state.failed_files.pop(file_key, None)
    progress["completed_entry_indices"] = []
    progress["last_error"] = None
    _checkpoint_state(state, force=True)
    await _log_file_completion("processed")


async def _async_mass_eval_main(
    input_path: str,
    mode: str,
    output_dir: str | None,
    state_file: str,
    resume: bool,
    relax_bibtex: bool,
    retry_forever: bool,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    checkpoint_interval_seconds: int = CHECKPOINT_INTERVAL_SECONDS,
    collect_cache_file: str | None = ".aletheia-probe/mass-eval-collect-cache.keys",
) -> None:
    """Run massive two-phase BibTeX evaluation workflow with checkpointing.

    Args:
        input_path: Path to a .bib file or directory containing .bib files
        mode: 'collect' or 'assess'
        output_dir: Output directory for assess mode JSONL records
        state_file: Checkpoint JSON file path
        resume: Whether to resume from an existing checkpoint
        relax_bibtex: Whether to use relaxed BibTeX parsing
        retry_forever: Retry indefinitely on transient backend failures
        max_concurrency: Number of concurrent entry workers per file
        checkpoint_interval_seconds: Maximum interval between forced checkpoints
    """
    status_logger = get_status_logger()
    detail_logger = get_detail_logger()

    try:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"collect", "assess"}:
            raise ValueError(f"Invalid mode: {mode}. Use 'collect' or 'assess'.")
        if max_concurrency < 1:
            raise ValueError(
                f"Invalid max_concurrency={max_concurrency}; expected value >= 1."
            )

        input_root = Path(input_path).expanduser().resolve()
        state_path = Path(state_file).expanduser().resolve()

        if normalized_mode == "assess":
            if not output_dir:
                raise ValueError("--output-dir is required in assess mode")
            output_root = Path(output_dir).expanduser().resolve()
            output_root.mkdir(parents=True, exist_ok=True)
        else:
            output_root = None

        collect_dedupe_cache: CollectDedupeCache | None = None
        if normalized_mode == "collect":
            cache_path = (
                Path(collect_cache_file).expanduser().resolve()
                if collect_cache_file
                else None
            )
            collect_dedupe_cache = await CollectDedupeCache.load(
                cache_path=cache_path,
                status_logger=status_logger,
                detail_logger=detail_logger,
            )

        bib_files = _discover_bib_files(input_root)
        state = _load_or_init_state(
            state_path=state_path,
            mode=normalized_mode,
            input_path=input_root,
            resume=resume,
            status_logger=status_logger,
        )

        completed = set(state.completed_files)
        pending_files = [path for path in bib_files if str(path) not in completed]

        status_logger.info(
            f"mass-eval mode={normalized_mode}, files_total={len(bib_files)}, "
            f"files_pending={len(pending_files)}, max_concurrency={max_concurrency}"
        )

        last_checkpoint_at = time.time()

        for index, bib_file in enumerate(pending_files, start=1):
            state.current_file = str(bib_file)
            status_logger.info(f"[{index}/{len(pending_files)}] Processing {bib_file}")

            try:
                await _process_single_file(
                    file_path=bib_file,
                    input_root=input_root,
                    mode=normalized_mode,
                    retry_forever=retry_forever,
                    relax_bibtex=relax_bibtex,
                    output_dir=output_root,
                    max_concurrency=max_concurrency,
                    state=state,
                    detail_logger=detail_logger,
                    status_logger=status_logger,
                    collect_dedupe_cache=collect_dedupe_cache,
                )
            except Exception as e:
                file_key = str(bib_file)
                state.failed_files[str(bib_file)] = str(e)
                file_progress = state.file_progress.setdefault(
                    file_key,
                    {"next_entry_index": 0, "written_records": 0, "last_error": None},
                )
                file_progress["last_error"] = str(e)
                status_logger.error(f"Failed processing {bib_file}: {e}")
                detail_logger.exception(f"mass-eval file failure: {bib_file}: {e}")

            now = time.time()
            if now - last_checkpoint_at >= checkpoint_interval_seconds:
                _checkpoint_state(state, force=True)
                if collect_dedupe_cache is not None:
                    await collect_dedupe_cache.flush()
                last_checkpoint_at = now

        state.current_file = None
        _checkpoint_state(state, force=True)
        if collect_dedupe_cache is not None:
            await collect_dedupe_cache.flush(force=True)

        status_logger.info(
            "mass-eval completed. "
            f"processed_entries={state.processed_entries}, "
            f"written_records={state.written_records}, "
            f"failed_files={len(state.failed_files)}, "
            f"collect_cache_hits={state.collect_cache_hits}"
        )

        sys.exit(0 if not state.failed_files else 1)

    except Exception as e:
        handle_cli_exception(e, verbose=True, context="mass evaluation")


__all__ = ["_async_mass_eval_main"]
