# SPDX-License-Identifier: MIT
"""Backend modules for journal assessment."""

# Import backends to register them
# scopus imported first since it takes the longest
from . import (
    algerian_ministry,
    bealls,
    cross_validator,
    crossref_analyzer,
    doaj,
    kscien_hijacked_journals,
    kscien_predatory_conferences,
    kscien_publishers,
    kscien_standalone_journals,
    openalex_analyzer,
    predatoryjournals,
    retraction_watch,
    scopus,
)


__all__ = [
    "bealls",
    "doaj",
    "algerian_ministry",
    "kscien_hijacked_journals",
    "kscien_predatory_conferences",
    "kscien_publishers",
    "kscien_standalone_journals",
    "predatoryjournals",
    "retraction_watch",
    "scopus",
    "openalex_analyzer",
    "crossref_analyzer",
    "cross_validator",
]
