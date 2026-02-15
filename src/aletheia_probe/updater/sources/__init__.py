# SPDX-License-Identifier: MIT
"""Data source implementations for journal list updates."""

from .algerian import AlgerianMinistrySource
from .bealls import BeallsListSource
from .core import CoreConferenceSource, CoreJournalSource
from .custom import CustomListSource
from .dblp import DblpVenueSource
from .kscien_generic import KscienGenericSource
from .kscien_hijacked_journals import KscienHijackedJournalsSource
from .kscien_publishers import KscienPublishersSource
from .kscien_standalone_journals import KscienStandaloneJournalsSource
from .predatoryjournals import PredatoryJournalsSource
from .retraction_watch import RetractionWatchSource
from .ror_snapshot import RorSnapshotSource
from .scopus import ScopusSource
from .ugc_care import (
    UgcCareClonedGroup2Source,
    UgcCareClonedSource,
    UgcCareDelistedGroup2Source,
    UgcCareIncludedFromCloneGroup1Source,
    UgcCareIncludedFromCloneGroup2Source,
)


__all__ = [
    "AlgerianMinistrySource",
    "BeallsListSource",
    "CustomListSource",
    "CoreConferenceSource",
    "CoreJournalSource",
    "DblpVenueSource",
    "KscienGenericSource",
    "KscienHijackedJournalsSource",
    "KscienPublishersSource",
    "KscienStandaloneJournalsSource",
    "PredatoryJournalsSource",
    "RetractionWatchSource",
    "RorSnapshotSource",
    "ScopusSource",
    "UgcCareClonedGroup2Source",
    "UgcCareClonedSource",
    "UgcCareDelistedGroup2Source",
    "UgcCareIncludedFromCloneGroup1Source",
    "UgcCareIncludedFromCloneGroup2Source",
]
