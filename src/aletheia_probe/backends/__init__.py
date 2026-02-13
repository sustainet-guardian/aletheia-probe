# SPDX-License-Identifier: MIT
"""Backend modules for journal assessment."""

# Import backends to register them
from . import (
    algerian_ministry,
    bealls,
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
    ugc_care_cloned,
    ugc_care_cloned_group2,
    ugc_care_delisted_group2,
)


__all__ = [
    "algerian_ministry",
    "bealls",
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
    "ugc_care_cloned",
    "ugc_care_cloned_group2",
    "ugc_care_delisted_group2",
]
