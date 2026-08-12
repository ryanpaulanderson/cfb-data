"""Export Pydantic models for Conferences endpoints."""

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
    "ConferencesRequest",
    "TeamConferenceAffiliation",
    "TeamConferenceChange",
]
