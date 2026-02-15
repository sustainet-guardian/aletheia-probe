# JOSS Submission Documentation

This directory contains all materials for submitting Aletheia-Probe to the [Journal of Open Source Software (JOSS)](https://joss.theoj.org/).

## Contents

- **paper.md** - JOSS paper in Markdown format with YAML metadata
- **paper.bib** - BibTeX bibliography with references
- **README.md** - This file, containing submission guidelines and checklist

## Building the Paper Locally

To build and preview the paper PDF locally, you need Pandoc and LaTeX:

### Install Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get install pandoc texlive-latex-base texlive-latex-extra texlive-fonts-recommended
```

**macOS:**
```bash
brew install pandoc
brew install --cask mactex
```

**Windows:**
- Install [Pandoc](https://pandoc.org/installing.html)
- Install [MiKTeX](https://miktex.org/download) or [TeX Live](https://www.tug.org/texlive/)

### Build the PDF

```bash
cd docs/JOSS
pandoc paper.md \
  --from=markdown \
  --to=pdf \
  --bibliography=paper.bib \
  --citeproc \
  --output=paper.pdf \
  --pdf-engine=pdflatex \
  -V geometry:margin=1in \
  -V fontsize=11pt
```

The CI/CD pipeline automatically builds the paper on every commit to validate formatting.

## Pre-Submission Checklist

Before submitting to JOSS, ensure the following requirements are met:

### Software Requirements

- [x] **Open source license**: MIT License (see LICENSE file)
- [x] **Public repository**: GitHub at https://github.com/sustainet-guardian/aletheia-probe
- [x] **Issue tracker**: GitHub Issues enabled and accessible without login
- [x] **Installation instructions**: Comprehensive documentation in README.md and docs/
- [x] **Usage examples**: Quick start guide and user documentation
- [x] **Test suite**: Full pytest suite with >80% coverage
- [x] **Community guidelines**: CONTRIBUTING.md, CODE_OF_CONDUCT.md
- [x] **Automated tests**: GitHub Actions CI/CD pipeline
- [x] **Archived release with DOI**: Create Zenodo release (see below)
- [x] **ORCID for all authors**: Update paper.md with correct ORCID IDs

### Paper Requirements

- [x] **YAML metadata**: Title, tags, authors, affiliations, date, bibliography
- [x] **Summary section**: Brief overview of software functionality
- [x] **Statement of Need**: Explains research problem and software solution
- [x] **References**: Citations to relevant literature and data sources
- [x] **Community guidelines**: Described in paper and repository
- [x] **Acknowledgments**: Funding acknowledgment included
- [x] **Length check**: 250-1000 words (excluding references),
- [x] **All citations valid**: Verify all DOIs and URLs work

### Repository Requirements

- [x] **README with badges**: CI/CD, license, Python version, DOI (Zenodo)
- [x] **Documentation**: User guide, API reference, troubleshooting
- [x] **Installation method**: Available on PyPI (`pip install aletheia-probe`)
- [x] **Version controlled**: Git with meaningful commit history
- [x] **Substantial code**: ~5000+ lines of Python code across multiple modules
- [x] **Mature project**: Active development, multiple releases (v0.6.0)

## Submission Process

Once all requirements are met:

### 1. Submit to JOSS

1. Go to https://joss.theoj.org/papers/new
2. Fill in the submission form:
   - **Repository URL**: https://github.com/sustainet-guardian/aletheia-probe
   - **Version**: v0.9.0 (or latest release)
   - **Archive DOI**: Your Zenodo DOI
   - **Editor suggestions**: (optional) Editors with expertise in research software, scientific publishing, or bibliometrics
3. Submit the form

### 2. Pre-Review

An Associate Editor-in-Chief will:
- Verify the submission meets basic requirements
- Check that software is in scope for JOSS
- Assign a handling editor (usually within 1-2 weeks)

### 3. Review Process

The handling editor will:
- Assign 2+ reviewers
- Open a review issue in https://github.com/openjournals/joss-reviews
- Reviewers will test installation, documentation, and functionality
- Reviews are open and conversational

### 4. Respond to Reviews

Authors must:
- Respond to reviewer comments within 2 weeks
- Implement requested changes within 4-6 weeks
- Update the paper and software as needed
- Tag new releases for significant changes

### 5. Acceptance

Upon successful review:
- Create final tagged release
- Update Zenodo archive
- Provide version number and DOI to reviewers
- JOSS assigns paper DOI and publishes

## Expected Timeline

- **Submission to pre-review**: 0-2 weeks
- **Pre-review to editor assignment**: 1-2 weeks
- **Review process**: 4-8 weeks (depends on reviewer availability)
- **Revisions**: 4-6 weeks (depends on scope of changes)
- **Total**: ~3-4 months from submission to publication

## JOSS Review Criteria

Reviewers will check:

### Software Functionality
- [ ] Installation works on reviewer's system
- [ ] Software runs without errors
- [ ] Core functionality works as documented
- [ ] Examples execute successfully

### Documentation
- [ ] Installation instructions are clear
- [ ] Usage examples are provided
- [ ] API is documented (if applicable)
- [ ] Community guidelines exist

### Software Quality
- [ ] Automated tests exist and pass
- [ ] Code is readable and well-structured
- [ ] Dependencies are appropriate
- [ ] License is clearly stated

### Paper Quality
- [ ] Summary accurately describes software
- [ ] Statement of need is compelling
- [ ] References are appropriate
- [ ] Length is suitable (not too short or long)

## Additional Resources

- **JOSS Documentation**: https://joss.readthedocs.io/
- **Author Guide**: https://joss.readthedocs.io/en/latest/submitting.html
- **Review Criteria**: https://joss.readthedocs.io/en/latest/review_criteria.html
- **Reviewer Guidelines**: https://joss.readthedocs.io/en/latest/reviewer_guidelines.html
- **Example Papers**: https://github.com/openjournals/joss-papers

## Questions or Issues?

- **JOSS submission questions**: admin@theoj.org
- **Software questions**: https://github.com/sustainet-guardian/aletheia-probe/issues
- **Review process**: Ask in your JOSS review issue thread

## Status

**Current Status**: Ready for Zenodo archiving and ORCID updates

**Remaining Tasks**:
3. Add Zenodo DOI to paper.md and README.md
4. Final review of paper content
5. Submit to JOSS

**Notes**: The software meets all JOSS requirements for substantial scholarly effort (~5000+ LOC, multiple backends, comprehensive testing, active development history). The paper provides clear motivation and describes the architecture.
