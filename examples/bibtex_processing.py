#!/usr/bin/env python3
"""
BibTeX processing examples using the Aletheia Probe Python API.

This script demonstrates:
1. BibTeX file processing
2. Journal extraction and assessment
3. Result aggregation and reporting
"""

import asyncio
import tempfile
from pathlib import Path
from aletheia_probe.batch_assessor import BibtexBatchAssessor


def create_sample_bibtex():
    """Create a sample BibTeX file for demonstration."""
    bibtex_content = """
@article{smith2023nature,
    title={A groundbreaking study},
    author={Smith, John},
    journal={Nature Communications},
    volume={14},
    year={2023},
    issn={2041-1723}
}

@article{doe2023plos,
    title={Another important study},
    author={Doe, Jane},
    journal={PLOS ONE},
    volume={18},
    year={2023},
    issn={1932-6203}
}

@article{unknown2023suspicious,
    title={Suspicious research},
    author={Unknown, Author},
    journal={International Journal of Advanced Research},
    volume={1},
    year={2023}
}
"""

    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False)
    temp_file.write(bibtex_content)
    temp_file.close()

    return Path(temp_file.name)


async def process_bibtex_file():
    """Process a BibTeX file and assess all journals."""
    print("=== BibTeX File Processing ===")

    # Create sample BibTeX file
    bibtex_path = create_sample_bibtex()
    print(f"Created sample BibTeX file: {bibtex_path}")

    try:
        # Initialize the batch assessor
        assessor = BibtexBatchAssessor()

        # Process the BibTeX file
        result = await assessor.assess_bibtex_file(bibtex_path, verbose=True)

        # Display summary results
        print(f"\n=== Assessment Summary ===")
        print(f"Total entries processed: {result.total_entries}")
        print(f"Legitimate journals: {result.legitimate_count}")
        print(f"Predatory journals: {result.predatory_count}")
        print(f"Unknown/unclear: {result.unknown_count}")

        return result

    finally:
        # Clean up temporary file
        bibtex_path.unlink()


async def analyze_results(result):
    """Analyze and display detailed results."""
    print("\n=== Detailed Results ===")

    for entry in result.entries:
        print(f"\nJournal: {entry.journal_name}")
        print(f"  Assessment: {entry.assessment}")
        print(f"  Confidence: {entry.confidence:.0%}")

        if entry.retracted:
            print(f"  Warning: Contains retracted articles")

        if entry.assessment == "predatory":
            print(f"  Risk Level: HIGH - Avoid this journal")
        elif entry.assessment == "legitimate":
            print(f"  Risk Level: LOW - Safe to publish")
        else:
            print(f"  Risk Level: UNKNOWN - Requires manual review")


async def main():
    """Run all examples."""
    try:
        # Process BibTeX file
        result = await process_bibtex_file()

        # Analyze results
        await analyze_results(result)

        print("\n=== Processing Complete ===")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())