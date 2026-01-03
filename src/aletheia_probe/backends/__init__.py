# SPDX-License-Identifier: MIT
"""Backend modules for journal assessment."""

# Import backends to register them
from . import (
    algerian_ministry,
    bealls,
    cross_validator,
    crossref_analyzer,
    custom_list,
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
    "algerian_ministry",
    "bealls",
    "cross_validator",
    "crossref_analyzer",
    "custom_list",
    "doaj",
    "kscien_hijacked_journals",
    "kscien_predatory_conferences",
    "kscien_publishers",
    "kscien_standalone_journals",
    "openalex_analyzer",
    "predatoryjournals",
    "retraction_watch",
    "scopus",
]
