"""Validate responses from implemented CFBD Conferences endpoints."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from cfb_data._catalog.models import ConferenceAffiliationFact, ConferenceFact
from cfb_data._catalog.projection import (
    CatalogSink,
    IdentityAttribute,
    IdentityKey,
    ObservationAuthority,
    ProjectionContext,
    ValueTransform,
    observe_team,
)


class ConferenceClassification(StrEnum):
    """Identify an official conference division classification."""

    fbs = "fbs"
    fcs = "fcs"
    ii = "ii"
    ii_or_iii = "ii/iii"
    iii = "iii"


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to response models."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Conference(_ResponseModel):
    """Represent a conference and its membership count."""

    id: Annotated[
        int,
        IdentityKey(
            ConferenceFact,
            "id",
            transform=ValueTransform.positive_int,
            authority=ObservationAuthority.authoritative,
        ),
    ] = Field(gt=0)
    name: Annotated[
        str,
        IdentityAttribute(
            ConferenceFact,
            "name",
            transform=ValueTransform.nonempty_text,
            authority=ObservationAuthority.authoritative,
        ),
    ]
    short_name: str | None = Field(alias="shortName")
    abbreviation: Annotated[
        str | None,
        IdentityAttribute(
            ConferenceFact,
            "abbreviation",
            authority=ObservationAuthority.authoritative,
        ),
    ]
    classification: Annotated[
        ConferenceClassification | None,
        IdentityAttribute(
            ConferenceFact,
            "classification",
            transform=ValueTransform.enum_text,
            authority=ObservationAuthority.authoritative,
        ),
    ]
    member_count: int = Field(alias="memberCount", ge=0)


class TeamConferenceAffiliation(_ResponseModel):
    """Represent one historical team-to-conference affiliation."""

    team_id: int = Field(alias="teamId", gt=0)
    team: str
    conference_id: int = Field(alias="conferenceId", gt=0)
    conference: str
    conference_abbreviation: str | None = Field(alias="conferenceAbbreviation")
    classification: ConferenceClassification | None
    conference_division: str | None = Field(alias="conferenceDivision")
    start_year: int = Field(alias="startYear", ge=1869)
    end_year: int | None = Field(alias="endYear", ge=1869)

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project both entities and the explicit affiliation interval."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        observe_team(sink, id=self.team_id, school=self.team, source=source)
        sink.add(
            ConferenceFact(
                self.conference_id,
                self.conference,
                self.conference_abbreviation,
                str(self.classification) if self.classification else None,
            ),
            source=source,
        )
        sink.add(
            ConferenceAffiliationFact(
                self.team_id,
                self.conference_id,
                self.start_year,
                self.end_year,
            ),
            authority=ObservationAuthority.authoritative,
            source=source,
            observed_fields=frozenset(
                ("team_id", "conference_id", "start_year", "end_year")
            ),
        )


class TeamConferenceChange(_ResponseModel):
    """Represent one team's conference change for a season."""

    team_id: int = Field(alias="teamId", gt=0)
    team: str
    from_conference_id: int = Field(alias="fromConferenceId", gt=0)
    from_conference: str = Field(alias="fromConference")
    from_conference_abbreviation: str | None = Field(alias="fromConferenceAbbreviation")
    from_classification: ConferenceClassification | None = Field(
        alias="fromClassification"
    )
    to_conference_id: int = Field(alias="toConferenceId", gt=0)
    to_conference: str = Field(alias="toConference")
    to_conference_abbreviation: str | None = Field(alias="toConferenceAbbreviation")
    to_classification: ConferenceClassification | None = Field(alias="toClassification")
    effective_year: int = Field(alias="effectiveYear", ge=1869)

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project both sides of one conference transition."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        observe_team(sink, id=self.team_id, school=self.team, source=source)
        sink.add(
            ConferenceFact(
                self.from_conference_id,
                self.from_conference,
                self.from_conference_abbreviation,
                str(self.from_classification) if self.from_classification else None,
            ),
            source=source,
        )
        sink.add(
            ConferenceFact(
                self.to_conference_id,
                self.to_conference,
                self.to_conference_abbreviation,
                str(self.to_classification) if self.to_classification else None,
            ),
            source=source,
        )
        sink.add(
            ConferenceAffiliationFact(
                self.team_id,
                self.to_conference_id,
                self.effective_year,
            ),
            source=source,
        )
