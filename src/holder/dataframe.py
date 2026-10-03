"""Optional pandas conversion for detached Holder record contracts."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence, TypedDict, cast

if TYPE_CHECKING:
    import pandas as pd


class DataFrames(TypedDict):
    """Named detached tables returned by Context.to_dataframes()."""

    projects: pd.DataFrame
    cards: pd.DataFrame
    connections: pd.DataFrame
    tags: pd.DataFrame
    milestones: pd.DataFrame


_TIMESTAMP_FIELDS = frozenset({"created_at", "updated_at", "deleted_at", "start_at", "end_at"})
_FLOAT_FIELDS = frozenset({"sort_key"})


def _require_pandas() -> ModuleType:
    try:
        return import_module("pandas")
    except ModuleNotFoundError as error:
        if error.name != "pandas":
            raise
        raise ModuleNotFoundError(
            "pandas is required for DataFrame support; install it with "
            '"pip install holder[pandas]" (or "pip install -e \'.[pandas]\'" '
            "from a source checkout)"
        ) from None


def records_to_dataframe(
    records: Iterable[Mapping[str, object]], columns: Sequence[str]
) -> pd.DataFrame:
    """Copy detached records into a predictably typed pandas DataFrame."""

    pandas = _require_pandas()
    frame = pandas.DataFrame.from_records(records, columns=columns)

    for column in columns:
        if column in _TIMESTAMP_FIELDS:
            frame[column] = pandas.to_datetime(
                frame[column], unit="s", utc=True
            ).astype("datetime64[ns, UTC]")
        elif column in _FLOAT_FIELDS:
            frame[column] = frame[column].astype("float64")
        elif column in {"editable", "all_day"}:
            frame[column] = frame[column].astype("boolean")
        else:
            frame[column] = frame[column].astype("string")

    return cast("pd.DataFrame", frame)


__all__ = ["DataFrames", "records_to_dataframe"]
