from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Union

import numpy as np

TimeLike = Union[int, np.integer, np.datetime64, datetime]

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ONE_US = timedelta(microseconds=1)
_TICKS_PER_US = {"ns": 1_000, "ps": 1_000_000, "fs": 1_000_000_000, "as": 1_000_000_000_000}


class TimeRange(NamedTuple):
    """The samples' time span as a ``start <= t < end`` window, in microseconds since the epoch (UTC).

    ``start_us`` is the first sample and ``end_us`` is one microsecond after the
    last, so ``rec.read(signal, *time_range)`` returns every row. ``start`` and
    ``end`` give the same bounds as UTC datetimes.
    """

    start_us: int
    end_us: int

    @property
    def last_us(self) -> int:
        """Time of the last sample."""
        return self.end_us - 1

    @property
    def start(self) -> datetime:
        return _EPOCH + timedelta(microseconds=self.start_us)

    @property
    def end(self) -> datetime:
        return _EPOCH + timedelta(microseconds=self.end_us)

    @property
    def duration(self) -> timedelta:
        return timedelta(microseconds=self.end_us - self.start_us)

    def __repr__(self) -> str:
        return f"TimeRange({_iso(self.start)} -> {_iso(self.end)}, {self.duration})"


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def to_epoch_us(value: TimeLike) -> int:
    """Convert a time to integer microseconds since the Unix epoch (UTC).

    Integers are taken as microseconds already. Naive datetimes are read as UTC,
    matching the file's timestamps. Sub-microsecond times round up to the next
    microsecond, so ``start <= t < end`` keeps its meaning against the file's
    integer-microsecond timestamps.
    """
    if isinstance(value, (bool, np.bool_)):
        raise TypeError("expected a time, got a bool")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if hasattr(value, "to_datetime64"):
        # pandas.Timestamp: to_datetime64() is the UTC instant for tz-aware values.
        return _datetime64_to_us(value.to_datetime64())
    if isinstance(value, np.datetime64):
        return _datetime64_to_us(value)
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return (aware - _EPOCH) // _ONE_US
    raise TypeError(
        f"expected int microseconds, datetime, numpy.datetime64 or pandas.Timestamp, got {type(value).__name__}"
    )


def _datetime64_to_us(value: np.datetime64) -> int:
    if np.isnat(value):
        raise ValueError("cannot use NaT as a time bound")
    unit, count = np.datetime_data(value.dtype)
    ticks_per_us = _TICKS_PER_US.get(unit)
    if ticks_per_us is None:
        return int(value.astype("datetime64[us]").astype(np.int64))
    ticks = int(value.astype(np.int64)) * count
    return -(-ticks // ticks_per_us)
