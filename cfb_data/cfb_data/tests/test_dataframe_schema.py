"""Test explicit logical-schema failure behavior for unsupported annotations."""

import pytest
from cfb_data._dataframes import _PandasAdapter, _PolarsAdapter
from cfb_data.errors import CFBDDataFrameConversionError
from pydantic import BaseModel


class _UnsupportedRow(BaseModel):
    """Provide a mapping annotation with no backend-neutral table contract."""

    payload: dict[str, int]


@pytest.mark.parametrize(
    ("adapter", "backend"),
    [(_PandasAdapter(), "pandas"), (_PolarsAdapter(), "polars")],
)
def test_unsupported_annotation_fails_without_object_fallback(
    adapter: object,
    backend: str,
) -> None:
    with pytest.raises(CFBDDataFrameConversionError) as exc_info:
        adapter.from_models(
            endpoint="/unsupported",
            row_model=_UnsupportedRow,
            models=[_UnsupportedRow(payload={"value": 1})],
        )

    assert exc_info.value.backend == backend
    assert exc_info.value.endpoint == "/unsupported"
