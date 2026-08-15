"""Export Pydantic models for Conferences endpoints."""

from .identity import ConferenceIdentity
from .requests import (
    ConferenceAffiliationsRequest,
    ConferenceChangesRequest,
    ConferencesRequest,
)
from .responses import (
    Conference,
    ConferenceClassification,
    TeamConferenceAffiliation,
    TeamConferenceChange,
)

__all__ = [
    "Conference",
    "ConferenceAffiliationsRequest",
    "ConferenceChangesRequest",
    "ConferenceClassification",
    "ConferenceIdentity",
    "ConferencesRequest",
    "TeamConferenceAffiliation",
    "TeamConferenceChange",
]
