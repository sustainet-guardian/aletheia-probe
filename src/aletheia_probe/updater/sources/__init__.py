# SPDX-License-Identifier: MIT
"""Data source implementations for journal list updates."""

from .algerian import AlgerianMinistrySource
from .bealls import BeallsListSource
from .custom import CustomListSource
from .kscien_hijacked_journals import KscienHijackedJournalsSource
from .kscien_predatory_conferences import KscienPredatoryConferencesSource
from .kscien_publishers import KscienPublishersSource
from .kscien_standalone_journals import KscienStandaloneJournalsSource
from .predatoryjournals import PredatoryJournalsSource
from .retraction_watch import RetractionWatchSource
from .scopus import ScopusSource

__all__ = [
    "AlgerianMinistrySource",
    "BeallsListSource",
    "CustomListSource",
    "KscienHijackedJournalsSource",
    "KscienPredatoryConferencesSource",
    "KscienPublishersSource",
    "KscienStandaloneJournalsSource",
    "PredatoryJournalsSource",
    "RetractionWatchSource",
    "ScopusSource",
]
