# SPDX-License-Identifier: MIT
"""Data source implementations for journal list updates."""

from .algerian import AlgerianMinistrySource
from .bealls import BeallsListSource
from .custom import CustomListSource
from .kscien_generic import KscienGenericSource
from .kscien_hijacked_journals import KscienHijackedJournalsSource
from .kscien_publishers import KscienPublishersSource
from .kscien_standalone_journals import KscienStandaloneJournalsSource
from .predatoryjournals import PredatoryJournalsSource
from .retraction_watch import RetractionWatchSource
from .scopus import ScopusSource


__all__ = [
    "AlgerianMinistrySource",
    "BeallsListSource",
    "CustomListSource",
    "KscienGenericSource",
    "KscienHijackedJournalsSource",
    "KscienPublishersSource",
    "KscienStandaloneJournalsSource",
    "PredatoryJournalsSource",
    "RetractionWatchSource",
    "ScopusSource",
]
