#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Basic journal assessment examples using the Aletheia Probe Python API.

This script demonstrates:
1. Single journal assessment
2. Batch assessment of multiple journals
3. Result interpretation examples
"""

import asyncio
from aletheia_probe import query_dispatcher
from aletheia_probe.models import QueryInput


async def single_assessment():
    """Assess a single journal and interpret results."""
    print("=== Single Journal Assessment ===")

    # Create query for Nature Communications
    query = QueryInput(
        raw_input="Nature Communications",
        normalized_name="nature communications",
        identifiers={"issn": "2041-1723"}
    )

    # Perform assessment
    result = await query_dispatcher.assess_journal(query)

    # Display results
    print(f"Journal: {query.raw_input}")
    print(f"Assessment: {result.assessment}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Backend Results: {len(result.backend_results)} sources checked")

    return result


async def batch_assessment():
    """Assess multiple journals in batch."""
    print("\n=== Batch Assessment ===")

    # List of journals to assess
    journals = [
        {"name": "Science", "issn": "1095-9203"},
        {"name": "PLOS ONE", "issn": "1932-6203"},
        {"name": "Journal of Biomedicine", "issn": None}  # Potentially suspicious
    ]

    results = []

    for journal in journals:
        query = QueryInput(
            raw_input=journal["name"],
            normalized_name=journal["name"].lower(),
            identifiers={"issn": journal["issn"]} if journal["issn"] else {}
        )

        result = await query_dispatcher.assess_journal(query)
        results.append((journal["name"], result))

        print(f"{journal['name']}: {result.assessment} ({result.confidence:.0%} confidence)")

    return results


async def main():
    """Run all examples."""
    try:
        # Single assessment
        await single_assessment()

        # Batch assessment
        await batch_assessment()

        print("\n=== Assessment Complete ===")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())