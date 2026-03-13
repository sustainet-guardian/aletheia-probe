# SPDX-License-Identifier: MIT
"""Tests for mass evaluation workflow helpers."""

from pathlib import Path

import pytest

from aletheia_probe.cli_logic import mass_eval
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import AssessmentResult, BibtexEntry, VenueType


def test_advance_file_progress_tracks_sparse_completion() -> None:
    """Advance contiguous index while preserving out-of-order completions."""
    progress: dict[str, object] = {"next_entry_index": 0}
    completed_indices = {0, 2, 3}

    mass_eval._advance_file_progress(progress, completed_indices, total_entries=5)
    assert progress["next_entry_index"] == 1
    assert progress["completed_entry_indices"] == [2, 3]

    completed_indices.add(1)
    mass_eval._advance_file_progress(progress, completed_indices, total_entries=5)
    assert progress["next_entry_index"] == 4
    assert progress["completed_entry_indices"] == []


@pytest.mark.asyncio
async def test_process_single_file_respects_sparse_resume_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not reprocess entries already marked complete in sparse resume state."""
    bib_file = tmp_path / "input.bib"
    bib_file.write_text("@article{a,title={x}}\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_file = output_dir / "input.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = [
        BibtexEntry(
            key="k0",
            journal_name="Journal 0",
            entry_type="article",
            venue_type=VenueType.JOURNAL,
        ),
        BibtexEntry(
            key="k1",
            journal_name="Journal 1",
            entry_type="article",
            venue_type=VenueType.JOURNAL,
        ),
        BibtexEntry(
            key="k2",
            journal_name="Journal 2",
            entry_type="article",
            venue_type=VenueType.JOURNAL,
        ),
    ]

    monkeypatch.setattr(
        mass_eval.BibtexParser,
        "parse_bibtex_file",
        lambda _path, relax_parsing=False: (entries, 0, 0),
    )

    existing_record_id = mass_eval._record_id_for_entry(bib_file, entries[2])
    output_file.write_text(
        f'{{"record_id":"{existing_record_id}"}}\n', encoding="utf-8"
    )

    async def _fake_assess(*_args, **_kwargs) -> AssessmentResult:
        return AssessmentResult(
            input_query="q",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.9,
            overall_score=0.9,
            backend_results=[],
            metadata=None,
            reasoning=[],
            processing_time=0.01,
        )

    monkeypatch.setattr(mass_eval, "_assess_with_retry", _fake_assess)

    state = mass_eval.MassEvalState(
        state_path=tmp_path / "state.json",
        mode="assess",
        input_path=bib_file,
    )
    state.file_progress[str(bib_file)] = {
        "next_entry_index": 1,
        "completed_entry_indices": [2],
        "written_records": 1,
        "last_error": None,
    }

    await mass_eval._process_single_file(
        file_path=bib_file,
        input_root=bib_file,
        mode="assess",
        retry_forever=False,
        relax_bibtex=False,
        output_dir=output_dir,
        max_concurrency=2,
        state=state,
        detail_logger=mass_eval.get_detail_logger(),
        status_logger=mass_eval.get_status_logger(),
    )

    assert state.processed_entries == 1
    progress = state.file_progress[str(bib_file)]
    assert progress["next_entry_index"] == 3
    assert progress["completed_entry_indices"] == []

    lines = [
        line for line in output_file.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_process_single_file_retries_parse_with_relaxed_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retry with relax_parsing=True when strict parse fails."""
    bib_file = tmp_path / "input.bib"
    bib_file.write_text("@article{a,title={x}}\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)

    entry = BibtexEntry(
        key="k0",
        journal_name="Journal 0",
        entry_type="article",
        venue_type=VenueType.JOURNAL,
    )
    parse_calls: list[bool] = []

    def _fake_parse(_path: Path, relax_parsing: bool = False):
        parse_calls.append(relax_parsing)
        if not relax_parsing:
            raise ValueError("duplicate doi field")
        return ([entry], 0, 0)

    monkeypatch.setattr(mass_eval.BibtexParser, "parse_bibtex_file", _fake_parse)

    async def _fake_assess(*_args, **_kwargs) -> AssessmentResult:
        return AssessmentResult(
            input_query="q",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.9,
            overall_score=0.9,
            backend_results=[],
            metadata=None,
            reasoning=[],
            processing_time=0.01,
        )

    monkeypatch.setattr(mass_eval, "_assess_with_retry", _fake_assess)

    state = mass_eval.MassEvalState(
        state_path=tmp_path / "state.json",
        mode="assess",
        input_path=bib_file,
    )

    await mass_eval._process_single_file(
        file_path=bib_file,
        input_root=bib_file,
        mode="assess",
        retry_forever=False,
        relax_bibtex=False,
        output_dir=output_dir,
        max_concurrency=1,
        state=state,
        detail_logger=mass_eval.get_detail_logger(),
        status_logger=mass_eval.get_status_logger(),
    )

    assert parse_calls == [False, True]
    assert state.processed_entries == 1


@pytest.mark.asyncio
async def test_process_single_file_collect_dedupes_repeated_venues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collect mode should skip repeated venue strings using dedupe cache."""
    bib_file = tmp_path / "input.bib"
    bib_file.write_text("@article{a,title={x}}\n", encoding="utf-8")

    entries = [
        BibtexEntry(
            key="k0",
            journal_name="International Conference on Language Resources and Evaluation",
            entry_type="inproceedings",
            venue_type=VenueType.CONFERENCE,
        ),
        BibtexEntry(
            key="k1",
            journal_name="International Conference on Language Resources and Evaluation",
            entry_type="inproceedings",
            venue_type=VenueType.CONFERENCE,
        ),
        BibtexEntry(
            key="k2",
            journal_name="Computational Linguistics",
            entry_type="article",
            venue_type=VenueType.JOURNAL,
        ),
    ]

    monkeypatch.setattr(
        mass_eval.BibtexParser,
        "parse_bibtex_file",
        lambda _path, relax_parsing=False: (entries, 0, 0),
    )

    collect_calls: list[str] = []

    async def _fake_collect(*_args, **kwargs) -> None:
        collect_calls.append(str(kwargs["venue_name"]))

    monkeypatch.setattr(mass_eval, "_collect_with_retry", _fake_collect)

    cache_file = tmp_path / "collect.keys"
    collect_cache = await mass_eval.CollectDedupeCache.load(
        cache_path=cache_file,
        status_logger=mass_eval.get_status_logger(),
        detail_logger=mass_eval.get_detail_logger(),
    )
    state = mass_eval.MassEvalState(
        state_path=tmp_path / "state.json",
        mode="collect",
        input_path=bib_file,
    )

    await mass_eval._process_single_file(
        file_path=bib_file,
        input_root=bib_file,
        mode="collect",
        retry_forever=False,
        relax_bibtex=False,
        output_dir=None,
        max_concurrency=3,
        state=state,
        detail_logger=mass_eval.get_detail_logger(),
        status_logger=mass_eval.get_status_logger(),
        collect_dedupe_cache=collect_cache,
    )
    await collect_cache.flush(force=True)

    assert len(collect_calls) == 2
    assert state.processed_entries == 3
    assert state.collect_cache_hits == 1

    persisted = [
        line for line in cache_file.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(persisted) == 2


@pytest.mark.asyncio
async def test_collect_dedupe_cache_reads_existing_keys_and_skips(
    tmp_path: Path,
) -> None:
    """Cache should be read at startup and avoid reprocessing known keys."""
    key_file = tmp_path / "collect.keys"
    key_file.write_text("abc123\n", encoding="utf-8")

    cache = await mass_eval.CollectDedupeCache.load(
        cache_path=key_file,
        status_logger=mass_eval.get_status_logger(),
        detail_logger=mass_eval.get_detail_logger(),
    )
    is_owner, wait_future = await cache.claim_or_wait("abc123")
    assert is_owner is False
    assert wait_future is None
