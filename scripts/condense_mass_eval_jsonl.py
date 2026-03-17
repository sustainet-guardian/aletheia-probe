# SPDX-License-Identifier: MIT
"""Create a condensed CSV view from mass-eval JSONL output."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _iter_jsonl_records(input_path: Path) -> Any:
    """Yield JSON objects from a JSONL file, skipping malformed lines."""
    with input_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                print(
                    f"[warn] Skipping malformed JSON at line {line_number}: {input_path}"
                )
                continue
            if isinstance(payload, dict):
                yield payload


def _collect_backend_names(input_path: Path) -> list[str]:
    """Collect unique backend names appearing in backend_results arrays."""
    backend_names: set[str] = set()
    for record in _iter_jsonl_records(input_path):
        backend_results = record.get("backend_results", [])
        if not isinstance(backend_results, list):
            continue
        for backend_result in backend_results:
            if not isinstance(backend_result, dict):
                continue
            backend_name = backend_result.get("backend_name")
            if isinstance(backend_name, str) and backend_name:
                backend_names.add(backend_name)
    return sorted(backend_names)


def _fmt_float(value: Any) -> Any:
    """Round float to 4 decimal places to avoid IEEE 754 noise and LibreOffice misreads."""
    if isinstance(value, float):
        return f"{round(value, 4):.4f}"
    return value


def _build_base_row(record: dict[str, Any]) -> dict[str, Any]:
    """Build CSV row with condensed top-level fields."""
    predatory_list_hits = record.get("predatory_list_hits", [])
    if not isinstance(predatory_list_hits, list):
        predatory_list_hits = []

    backend_results = record.get("backend_results", [])
    if not isinstance(backend_results, list):
        backend_results = []

    found_count = 0
    error_count = 0
    timeout_count = 0
    rate_limited_count = 0
    for backend_result in backend_results:
        if not isinstance(backend_result, dict):
            continue
        status = str(backend_result.get("status") or "").lower()
        if status == "found":
            found_count += 1
        elif status == "error":
            error_count += 1
        elif status == "timeout":
            timeout_count += 1
        elif status == "rate_limited":
            rate_limited_count += 1

    return {
        "entry_key": record.get("entry_key"),
        "venue_raw": record.get("venue_raw"),
        "venue_type": record.get("venue_type"),
        "doi": record.get("doi"),
        "issn": record.get("issn"),
        "eissn": record.get("eissn"),
        "state": record.get("state", "assessed"),
        "state_reason": record.get("state_reason"),
        "final_assessment": record.get("final_assessment"),
        "confidence": _fmt_float(record.get("confidence")),
        "overall_score": _fmt_float(record.get("overall_score")),
        "is_suspicious": record.get("is_suspicious"),
        "has_conflict": record.get("has_conflict"),
        "predatory_votes": record.get("predatory_votes"),
        "legitimate_votes": record.get("legitimate_votes"),
        "predatory_list_hits_count": len(predatory_list_hits),
        "found_backends_count": found_count,
        "error_backends_count": error_count,
        "timeout_backends_count": timeout_count,
        "rate_limited_backends_count": rate_limited_count,
    }


def _backend_cell_value(backend_result: dict[str, Any]) -> str:
    """Select compact result label for a backend."""
    assessment = backend_result.get("assessment")
    if isinstance(assessment, str) and assessment:
        return assessment

    status = backend_result.get("status")
    if isinstance(status, str) and status:
        return status

    return ""


def condense_jsonl_to_csv(
    input_path: Path,
    output_path: Path,
    backend_columns: int,
    include_non_found: bool,
) -> None:
    """Write condensed CSV from mass-eval JSONL."""
    backend_names = _collect_backend_names(input_path)

    base_fields = [
        "entry_key",
        "venue_raw",
        "venue_type",
        "doi",
        "issn",
        "eissn",
        "state",
        "state_reason",
        "final_assessment",
        "confidence",
        "overall_score",
        "is_suspicious",
        "has_conflict",
        "predatory_votes",
        "legitimate_votes",
        "predatory_list_hits_count",
        "found_backends_count",
        "error_backends_count",
        "timeout_backends_count",
        "rate_limited_backends_count",
    ]

    backend_fields: list[str] = []
    for backend_name in backend_names:
        backend_fields.append(f"{backend_name}_result")
        if backend_columns == 2:
            backend_fields.append(f"{backend_name}_confidence")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=base_fields + backend_fields)
        writer.writeheader()

        for record in _iter_jsonl_records(input_path):
            row = _build_base_row(record)
            backend_index: dict[str, dict[str, Any]] = {}
            backend_results = record.get("backend_results", [])
            if isinstance(backend_results, list):
                for backend_result in backend_results:
                    if not isinstance(backend_result, dict):
                        continue
                    backend_name = backend_result.get("backend_name")
                    if isinstance(backend_name, str) and backend_name:
                        backend_index[backend_name] = backend_result

            for backend_name in backend_names:
                result_key = f"{backend_name}_result"
                confidence_key = f"{backend_name}_confidence"
                backend_result = backend_index.get(backend_name)
                if not backend_result:
                    row[result_key] = ""
                    if backend_columns == 2:
                        row[confidence_key] = ""
                    continue

                status = str(backend_result.get("status") or "").lower()
                if not include_non_found and status != "found":
                    row[result_key] = ""
                    if backend_columns == 2:
                        row[confidence_key] = ""
                    continue

                row[result_key] = _backend_cell_value(backend_result)
                if backend_columns == 2:
                    confidence_value = backend_result.get("confidence")
                    row[confidence_key] = (
                        "" if confidence_value is None else _fmt_float(confidence_value)
                    )

            writer.writerow(row)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a condensed CSV from mass-eval JSONL with final assessment fields "
            "and per-backend result columns."
        )
    )
    parser.add_argument("input", type=Path, help="Path to input JSONL file")
    parser.add_argument("output", type=Path, help="Path to output CSV file")
    parser.add_argument(
        "--backend-columns",
        type=int,
        choices=(1, 2),
        default=2,
        help="Number of columns per backend: 1=result, 2=result+confidence",
    )
    parser.add_argument(
        "--include-non-found",
        action="store_true",
        help="Populate backend columns for all statuses, not only found results",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    input_path: Path = args.input.expanduser().resolve()
    output_path: Path = args.output.expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    condense_jsonl_to_csv(
        input_path=input_path,
        output_path=output_path,
        backend_columns=args.backend_columns,
        include_non_found=bool(args.include_non_found),
    )
    print(f"Wrote condensed CSV: {output_path}")


if __name__ == "__main__":
    main()
