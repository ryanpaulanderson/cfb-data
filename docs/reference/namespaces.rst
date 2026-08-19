Namespace API
=============

Each resource is available as a property on :class:`cfb_data.CFBDClient`.
Filtered methods accept either one positional request model or their explicit
snake-case keyword filters. See :doc:`../guides/requests` for the shared call
and validation contract.

Games
-----

.. autoclass:: cfb_data.games.resource.GamesResource
   :members:

Drives
------

.. autoclass:: cfb_data.drives.resource.DrivesResource
   :members:

Plays
-----

.. autoclass:: cfb_data.plays.resource.PlaysResource
   :members:

Venues
------

.. autoclass:: cfb_data.venues.resource.VenuesResource
   :members:

Conferences
-----------

.. autoclass:: cfb_data.conferences.resource.ConferencesResource
   :members:

Teams
-----

.. autoclass:: cfb_data.teams.resource.TeamsResource
   :members:

Stats
-----

.. autoclass:: cfb_data.stats.resource.StatsResource
   :members:

Metrics
-------

.. autoclass:: cfb_data.metrics.resource.MetricsResource
   :members:

Ratings
-------

.. autoclass:: cfb_data.ratings.resource.RatingsResource
   :members:

Players
-------

.. autoclass:: cfb_data.players.resource.PlayersResource
   :members:

Rankings
--------

.. autoclass:: cfb_data.rankings.resource.RankingsResource
   :members:

Betting
-------

.. autoclass:: cfb_data.betting.resource.BettingResource
   :members:

Recruiting
----------

.. autoclass:: cfb_data.recruiting.resource.RecruitingResource
   :members:

Coaches
-------

.. autoclass:: cfb_data.coaches.resource.CoachesResource
   :members:

Draft
-----

.. autoclass:: cfb_data.draft.resource.DraftResource
   :members:

Playoffs
--------

.. autoclass:: cfb_data.playoffs.resource.PlayoffsResource
   :members:

Adjusted metrics
----------------

.. autoclass:: cfb_data.adjusted_metrics.resource.AdjustedMetricsResource
   :members:

Info
----

.. autoclass:: cfb_data.info.resource.InfoResource
   :members:

Identities
----------

The identity namespace returns compact validated models rather than
DataFrames. See :doc:`../guides/cache-and-identities` for freshness and
hydration behavior.

.. autoclass:: cfb_data.identities.resource.IdentitiesResource
   :members:

.. autoclass:: cfb_data.identities.resource.TeamIdentities
   :members:

.. autoclass:: cfb_data.identities.resource.ConferenceIdentities
   :members:

.. autoclass:: cfb_data.identities.resource.VenueIdentities
   :members:

.. autoclass:: cfb_data.identities.resource.GameIdentities
   :members:

.. autoclass:: cfb_data.identities.resource.AthleteIdentities
   :members:

Datasets
--------

Curated methods return the configured eager DataFrame. The advanced methods
return durable execution evidence. See :doc:`../guides/datasets-and-workflows`.

.. autoclass:: cfb_data.analytics.datasets.DatasetsResource
   :members:

Workflows
---------

.. autoclass:: cfb_data.analytics.workflows.WorkflowsResource
   :members:
