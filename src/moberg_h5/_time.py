from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Union

import numpy as np

TimeLike = Union[int, np.integer, np.datetime64, datetime]

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ONE_US = timedelta(microseconds=1)


def to_epoch_us(value: TimeLike) -> int:
    """Convert a time to integer microseconds since the Unix epoch (UTC).

    Integers are taken as microseconds already. Naive datetimes are read as UTC,
    matching the file's timestamps.
    """
    if isinstance(value, (bool, np.bool_)):
        raise TypeError("expected a time, got a bool")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if hasattr(value, "to_datetime64"):
        # pandas.Timestamp: to_datetime64() is the UTC instant for tz-aware values.
        return int(value.to_datetime64().astype("datetime64[us]").astype(np.int64))
    if isinstance(value, np.datetime64):
        return int(value.astype("datetime64[us]").astype(np.int64))
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return (aware - _EPOCH) // _ONE_US
    raise TypeError(
        f"expected int microseconds, datetime, numpy.datetime64 or pandas.Timestamp, got {type(value).__name__}"
    )
