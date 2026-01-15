#!/bin/bash
# Build script for Aletheia-Probe arXiv paper
# Requires: pdflatex, bibtex

set -e

PAPER_NAME="AletheiaProbe-short"

echo "Building LaTeX document: $PAPER_NAME.tex"

# Cleanup from previous builds
echo "Cleaning up previous builds..."
rm -f *.aux *.bbl *.blg *.log *.out *.toc *.pdf

# First LaTeX run
echo "First LaTeX compilation..."
pdflatex $PAPER_NAME.tex

# BibTeX run for bibliography
echo "Processing bibliography..."
biber $PAPER_NAME

# Second LaTeX run to include bibliography
echo "Second LaTeX compilation..."
pdflatex $PAPER_NAME.tex

# Third LaTeX run to resolve cross-references
echo "Third LaTeX compilation for cross-references..."
pdflatex $PAPER_NAME.tex

# Check if PDF was generated successfully
if [ -f "$PAPER_NAME.pdf" ]; then
    echo "✓ PDF generated successfully: $PAPER_NAME.pdf"
    echo "File size: $(du -h $PAPER_NAME.pdf | cut -f1)"
    echo "Pages: $(pdfinfo $PAPER_NAME.pdf | grep Pages | awk '{print $2}')"
else
    echo "✗ Error: PDF generation failed"
    exit 1
fi

# Optional: Clean up auxiliary files (keep .bbl for arXiv submission)
echo "Cleaning up auxiliary files..."
rm -f *.aux *.blg *.log *.out *.toc *.bbl

echo "Build completed successfully!"
echo "Output: $PAPER_NAME.pdf"
