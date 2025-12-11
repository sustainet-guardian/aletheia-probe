#!/bin/bash
#
# Build JOSS paper locally
#
# This script builds the JOSS paper PDF from the Markdown source.
# It requires pandoc and LaTeX to be installed.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building JOSS paper..."
echo "====================="
echo ""

# Check for required tools
if ! command -v pandoc &> /dev/null; then
    echo "Error: pandoc is not installed"
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install pandoc"
    echo "  macOS: brew install pandoc"
    echo "  Windows: Download from https://pandoc.org/installing.html"
    exit 1
fi

if ! command -v pdflatex &> /dev/null; then
    echo "Error: pdflatex is not installed"
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install texlive-latex-base texlive-latex-extra"
    echo "  macOS: brew install --cask mactex"
    echo "  Windows: Download MiKTeX from https://miktex.org/download"
    exit 1
fi

# Build the PDF
echo "Building PDF with pandoc..."
pandoc paper.md \
  --from=markdown \
  --to=pdf \
  --bibliography=paper.bib \
  --citeproc \
  --output=paper.pdf \
  --pdf-engine=pdflatex \
  -V geometry:margin=1in \
  -V fontsize=11pt

if [ -f paper.pdf ]; then
    echo ""
    echo "✅ Success! Paper built: paper.pdf"
    echo ""

    # Count words
    word_count=$(sed '/^---$/,/^---$/d' paper.md | sed '/^# References/,$d' | wc -w | tr -d ' ')
    echo "Paper statistics:"
    echo "  Word count (excluding YAML and references): $word_count"

    if [ "$word_count" -lt 250 ]; then
        echo "  ⚠️  Warning: Paper might be too short (< 250 words)"
    elif [ "$word_count" -gt 1500 ]; then
        echo "  ⚠️  Warning: Paper might be too long (> 1500 words)"
    else
        echo "  ✅ Paper length is appropriate"
    fi

    # Check file size
    file_size=$(stat -f%z paper.pdf 2>/dev/null || stat -c%s paper.pdf 2>/dev/null)
    file_size_kb=$((file_size / 1024))
    echo "  PDF size: ${file_size_kb} KB"

    echo ""
    echo "You can now review the PDF:"
    if command -v xdg-open &> /dev/null; then
        echo "  xdg-open paper.pdf"
    elif command -v open &> /dev/null; then
        echo "  open paper.pdf"
    else
        echo "  (Open paper.pdf in your PDF viewer)"
    fi
else
    echo "❌ Error: Failed to build paper.pdf"
    exit 1
fi
