"""Validate responses from implemented CFBD Draft endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from cfb_data._catalog.models import VocabularyFact
from cfb_data._catalog.projection import (
    CatalogSink,
    ObservationAuthority,
    ProjectionContext,
    observe_athlete,
    observe_team,
)


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Draft responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class DraftTeam(_ResponseModel):
    """Represent an NFL team present in the historical draft data."""

    location: str
    nickname: str | None
    display_name: str | None = Field(alias="displayName")
    logo: str | None

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one NFL team vocabulary value."""
        name = self.display_name or self.location
        sink.add(
            VocabularyFact("draft_team", name, name),
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class DraftPosition(_ResponseModel):
    """Represent an NFL Draft position category."""

    name: str
    abbreviation: str

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one draft-position vocabulary value."""
        sink.add(
            VocabularyFact(
                "draft_position", self.abbreviation, self.name, self.abbreviation
            ),
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class DraftPickHometown(_ResponseModel):
    """Represent the recorded hometown of an NFL Draft pick."""

    city: str | None
    state: str | None
    country: str | None
    latitude: str | None
    longitude: str | None
    county_fips: str | None = Field(alias="countyFips")


class DraftPick(_ResponseModel):
    """Represent one historical NFL Draft selection."""

    college_athlete_id: int | None = Field(alias="collegeAthleteId", gt=0)
    nfl_athlete_id: int = Field(alias="nflAthleteId", gt=0)
    college_id: int = Field(alias="collegeId", gt=0)
    college_team: str = Field(alias="collegeTeam")
    college_conference: str | None = Field(alias="collegeConference")
    nfl_team_id: int = Field(alias="nflTeamId", gt=0)
    nfl_team: str = Field(alias="nflTeam")
    year: int = Field(ge=1936)
    overall: int = Field(gt=0)
    round: int = Field(gt=0)
    pick: int = Field(gt=0)
    name: str
    position: str
    height: float | None = Field(ge=0)
    weight: int | None = Field(ge=0)
    pre_draft_ranking: int | None = Field(alias="preDraftRanking", gt=0)
    pre_draft_position_ranking: int | None = Field(
        alias="preDraftPositionRanking", gt=0
    )
    pre_draft_grade: int | None = Field(alias="preDraftGrade", ge=0)
    hometown_info: DraftPickHometown = Field(alias="hometownInfo")

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project linked college athlete, school, and NFL identities."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        if self.college_athlete_id is not None:
            observe_athlete(
                sink,
                id=str(self.college_athlete_id),
                name=self.name,
                position=self.position,
                source=source,
            )
        observe_team(
            sink,
            id=self.college_id,
            school=self.college_team,
            source=source,
        )
        sink.add(
            VocabularyFact("nfl_athlete", str(self.nfl_athlete_id), self.name),
            source=source,
        )
        sink.add(
            VocabularyFact("draft_team", str(self.nfl_team_id), self.nfl_team),
            source=source,
        )


__all__ = ["DraftPick", "DraftPickHometown", "DraftPosition", "DraftTeam"]
