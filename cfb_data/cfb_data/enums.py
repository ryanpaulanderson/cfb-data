"""Define values shared by CFBD requests and responses."""

from enum import StrEnum

from ._reference_enums import (
    REFERENCE_SEASON,
    ConferenceName,
    TeamName,
    conferences,
    teams,
)


class SeasonType(StrEnum):
    """Identify the phase of a college football season."""

    regular = "regular"
    postseason = "postseason"
    both = "both"
    allstar = "allstar"
    spring_regular = "spring_regular"
    spring_postseason = "spring_postseason"


class Classification(StrEnum):
    """Identify a college football division classification."""

    fbs = "fbs"
    fcs = "fcs"
    ii = "ii"
    iii = "iii"


class RankingPoll(StrEnum):
    """Identify a supported rankings poll selector."""

    cfp = "cfp"


class RecruitClassification(StrEnum):
    """Identify the source classification of a recruit."""

    juco = "JUCO"
    prep_school = "PrepSchool"
    high_school = "HighSchool"


class MediaType(StrEnum):
    """Identify a game broadcast medium."""

    tv = "tv"
    radio = "radio"
    web = "web"
    ppv = "ppv"
    mobile = "mobile"


class PlayoffCompetition(StrEnum):
    """Identify an accepted playoff competition filter."""

    cfp = "cfp"


class PlayoffRound(StrEnum):
    """Identify an accepted College Football Playoff round filter."""

    first_round = "first_round"
    quarterfinal = "quarterfinal"
    semifinal = "semifinal"
    championship = "championship"


class UserUsageApi(StrEnum):
    """Identify which product contributes to an account usage summary."""

    all = "all"
    cfb = "cfb"
    cbb = "cbb"


class TransferEligibility(StrEnum):
    """Identify a transfer player's recorded eligibility status."""

    withdrawn = "Withdrawn"
    tbd = "TBD"
    pending_appeal = "PendingAppeal"
    sitting_one = "SittingOne"
    immediate = "Immediate"


__all__ = [
    "Classification",
    "ConferenceName",
    "MediaType",
    "PlayoffCompetition",
    "PlayoffRound",
    "RankingPoll",
    "REFERENCE_SEASON",
    "RecruitClassification",
    "SeasonType",
    "TeamName",
    "TransferEligibility",
    "UserUsageApi",
    "conferences",
    "teams",
]
