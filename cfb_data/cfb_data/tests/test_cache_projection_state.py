"""Test projection-contract state across local cache backends."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cfb_data._catalog.models import CatalogProjection, CoverageRecord, CoverageStatus
from cfb_data._catalog.sources import projection_contract
from cfb_data.cache._models import ResponseRecord
from cfb_data.cache._null import NullCacheBackend
from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.cache.config import SQLiteCacheConfig


def _record(now: datetime) -> ResponseRecord:
    """Return one retained response record for projection-state tests."""
    return ResponseRecord(
        key="e" * 64,
        endpoint="/teams",
        response_contract="Team:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now - timedelta(days=1),
        retained_until=now + timedelta(days=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )


def _projection(
    now: datetime, record: ResponseRecord, *, contract: str
) -> CatalogProjection:
    """Return coverage carrying an explicit projection contract."""
    return CatalogProjection(
        coverage=CoverageRecord(
            partition_key="/teams:",
            namespace="team",
            canonical_filters="",
            capabilities=("team.core_identity",),
            status=CoverageStatus.complete,
            response_key=record.key,
            endpoint=record.endpoint,
            fetched_at=now,
            validated_at=now,
            fresh_until=record.fresh_until,
            retained_until=record.retained_until,
            row_count=0,
            known_cap=None,
            projection_contract=contract,
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_kind", ["transient", "sqlite"])
async def test_projection_state_depends_only_on_the_stored_contract(
    backend_kind: str,
    tmp_path: Path,
) -> None:
    """Ignore response freshness while distinguishing absent and old markers."""
    now = datetime(2026, 8, 18, tzinfo=UTC)
    record = _record(now)
    backend = (
        NullCacheBackend()
        if backend_kind == "transient"
        else SQLiteCacheBackend(SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"))
    )
    await backend.open()

    assert not await backend.has_current_projection(
        endpoint="/teams", canonical_filters=""
    )
    await backend.commit_response(
        record,
        _projection(now, record, contract=projection_contract("/teams")),
    )
    assert await backend.has_current_projection(endpoint="/teams", canonical_filters="")
    assert not await backend.has_current_projection(
        endpoint="/teams", canonical_filters="conference='SEC'"
    )

    stale = _projection(now, record, contract="stale-contract")
    await backend.commit_response(record, stale)
    assert not await backend.has_current_projection(
        endpoint="/teams", canonical_filters=""
    )

    corrupt = _projection(now, record, contract="corrupt")
    await backend.commit_response(record, corrupt)
    assert not await backend.has_current_projection(
        endpoint="/teams", canonical_filters=""
    )

    await backend.close()
