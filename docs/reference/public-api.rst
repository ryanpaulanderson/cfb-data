Public API
==========

Client
------

.. autoclass:: cfb_data.CFBDClient
   :members:

.. autodata:: cfb_data.DataFrameBackend

Retry policy
------------

.. autoclass:: cfb_data.RetryPolicy
   :members:

Cache configuration
-------------------

.. autoclass:: cfb_data.SQLiteCacheConfig
   :members:

.. autoclass:: cfb_data.RedisCacheConfig
   :members:

.. autoclass:: cfb_data.CachePolicyConfig
   :members:

.. autoclass:: cfb_data.CacheTTL
   :members:

.. autoclass:: cfb_data.CacheProfile
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CacheMode
   :members:
   :show-inheritance:

Retrieval observability
-----------------------

.. autoclass:: cfb_data.RetrievalStats
   :members:

.. autoclass:: cfb_data.RetrievalStatsSnapshot
   :members:

.. autoclass:: cfb_data.EndpointRetrievalStats
   :members:

.. autoclass:: cfb_data.RetrievalObserver
   :members:

.. autodata:: cfb_data.RetrievalEvent

Identity results
----------------

.. autoclass:: cfb_data.TeamIdentity
   :members:

.. autoclass:: cfb_data.ConferenceIdentity
   :members:

.. autoclass:: cfb_data.VenueIdentity
   :members:

.. autoclass:: cfb_data.GameIdentity
   :members:

.. autoclass:: cfb_data.AthleteIdentity
   :members:

.. autoclass:: cfb_data.HydrationPlan
   :members:

.. autoclass:: cfb_data.FreshnessMode
   :members:
   :show-inheritance:

Exceptions
----------

.. autoclass:: cfb_data.CFBDError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDConfigurationError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDOptionalDependencyError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDCacheError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDCacheBackendError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDCacheMissError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDIdentityNotFoundError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDIdentityAmbiguityError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDClientStateError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDRequestValidationError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDTimeoutError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDTLSError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDTransportError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDHTTPError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDAuthenticationError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDAuthorizationError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDRateLimitError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDServerError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDResponseDecodeError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDResponseValidationError
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.CFBDDataFrameConversionError
   :members:
   :show-inheritance:

Allowed values
--------------

.. autoclass:: cfb_data.TeamName
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.ConferenceName
   :members:
   :show-inheritance:

The same classes are available through the lowercase aliases ``teams`` and
``conferences`` in :mod:`cfb_data.enums`.

.. autoclass:: cfb_data.SeasonType
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.Classification
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.RankingPoll
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.RecruitClassification
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.MediaType
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.PlayoffCompetition
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.PlayoffRound
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.UserUsageApi
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.TransferEligibility
   :members:
   :show-inheritance:

Additional response enums
~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: cfb_data.ConferenceClassification
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.HomeAway
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.RushPass
   :members:
   :show-inheritance:

.. autoclass:: cfb_data.DownType
   :members:
   :show-inheritance:
