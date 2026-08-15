"""Export the supported Conferences namespace and public contracts."""

from .models.pydantic import (
    Conference,
    ConferenceAffiliationsRequest,
    ConferenceChangesRequest,
    ConferenceClassification,
    ConferenceIdentity,
    ConferencesRequest,
    TeamConferenceAffiliation,
    TeamConferenceChange,
)
from .resource import ConferencesResource

__all__ = [
    "Conference",
    "ConferenceAffiliationsRequest",
    "ConferenceChangesRequest",
    "ConferenceClassification",
    "ConferenceIdentity",
    "ConferencesRequest",
    "ConferencesResource",
    "TeamConferenceAffiliation",
    "TeamConferenceChange",
]
