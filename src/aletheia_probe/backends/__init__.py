# SPDX-License-Identifier: MIT
"""Backend modules for journal assessment."""

# Import backends to register them
from . import (
    algerian_ministry,
    bealls,
    core_conferences,
    core_journals,
    crossref_analyzer,
    custom_list,
    dblp_venues,
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
    ugc_care_included_from_clone_group1,
    ugc_care_included_from_clone_group2,
)


__all__ = [
    "algerian_ministry",
    "bealls",
    "core_conferences",
    "core_journals",
    "crossref_analyzer",
    "dblp_venues",
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
    "ugc_care_included_from_clone_group1",
    "ugc_care_included_from_clone_group2",
]
