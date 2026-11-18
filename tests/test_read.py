from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from conftest import EEG_TIMESTAMPS, FP1_FIRST_ROW, GAP_AFTER, fp1_values

import moberg_h5
from moberg_h5._recording import _slice_bounds

TS = EEG_TIMESTAMPS


@pytest.mark.parametrize(
    ("start", "end", "rows"),
    [
        (None, None, range(10)),
        (TS[3], None, range(3, 10)),
        (TS[3] + 1, None, range(4, 10)),
        (TS[3] - 1, None, range(3, 10)),
        (None, TS[7], range(7)),
        (None, TS[7] + 1, range(8)),
        (TS[2], TS[5], range(2, 5)),
        (TS[0] - 10_000_000, TS[-1] + 10_000_000, range(10)),
        (TS[GAP_AFTER] + 1, None, range(GAP_AFTER + 1, 10)),
        (TS[GAP_AFTER] + 1, TS[GAP_AFTER + 1], range(0)),
        (TS[4], TS[4], range(0)),
        (TS[6], TS[2], range(0)),
        (TS[-1] + 1, None, range(0)),
        (None, TS[0], range(0)),
    ],
)
def test_time_slice_edges(v1_path, start, end, rows):
    start = None if start is None else int(start)
    end = None if end is None else int(end)
    with moberg_h5.open(v1_path) as rec:
        timestamps, values = rec.read("EEG/C3", start, end)

    expected = np.array(list(rows), dtype=np.int64)
    np.testing.assert_array_equal(timestamps, TS[expected] if len(expected) else np.empty(0, np.int64))
    np.testing.assert_array_equal(values, expected.astype(np.float64))
    assert timestamps.dtype == np.int64


def test_time_types_are_equivalent(v1_path):
    start_us, end_us = int(TS[2]), int(TS[8])
    start_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=start_us)
    end_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=end_us)
    eastern = timezone(timedelta(hours=-5))

    variants = [
        (start_us, end_us),
        (np.int64(start_us), np.int64(end_us)),
        (start_dt, end_dt),
        (start_dt.astimezone(eastern), end_dt.astimezone(eastern)),
        (start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None)),
        (np.datetime64(start_us, "us"), np.datetime64(end_us, "us")),
        (pd.Timestamp(start_us, unit="us", tz="UTC").tz_convert("US/Pacific"), pd.Timestamp(end_us, unit="us")),
    ]
    with moberg_h5.open(v1_path) as rec:
        # pandas types Timestamp(...) as Timestamp | NaTType.
        results = [rec.read("EEG/C3", start, end)[0] for start, end in variants]  # ty: ignore[invalid-argument-type]

    for timestamps in results:
        np.testing.assert_array_equal(timestamps, TS[2:8])


def test_rejects_float_times(v1_path):
    with moberg_h5.open(v1_path) as rec, pytest.raises(TypeError):
        rec.read("EEG/C3", float(TS[2]))  # ty: ignore[invalid-argument-type]


def test_nan_rows_for_channel_absent_from_early_segments(v1_path):
    with moberg_h5.open(v1_path) as rec:
        timestamps, values = rec.read("EEG/Fp1")
        _, sliced = rec.read("EEG/Fp1", int(TS[FP1_FIRST_ROW - 1]), int(TS[FP1_FIRST_ROW + 1]))

    assert len(timestamps) == len(values) == 10
    assert np.isnan(values[:FP1_FIRST_ROW]).all()
    np.testing.assert_array_equal(values[FP1_FIRST_ROW:], fp1_values()[FP1_FIRST_ROW:])
    assert np.isnan(sliced[0]) and sliced[1] == 40.0


def test_two_dimensional_read(v1_path):
    with moberg_h5.open(v1_path) as rec:
        timestamps, values = rec.read("EEG/qEEG_DSA_Left")
    assert values.shape == (3, 4)
    assert len(timestamps) == 3


def test_binary_search_reads_few_timestamps():
    class CountingTimestamps:
        def __init__(self, values):
            self.values = values
            self.reads = 0

        def __getitem__(self, index):
            self.reads += 1
            return self.values[index]

    n = 1_000_000
    timestamps = CountingTimestamps(np.arange(n, dtype=np.int64) * 10)
    lo, hi = _slice_bounds(timestamps, n, 123_455, 9_000_000)  # ty: ignore[invalid-argument-type]
    assert (lo, hi) == (12_346, 900_000)
    assert timestamps.reads <= 2 * 21


def test_read_frame_eeg_channels(v1_path):
    with moberg_h5.open(v1_path) as rec:
        frame = rec.read_frame(rec.eeg_channels(), int(TS[3]), int(TS[7]))

    assert list(frame.columns) == ["C3", "C4", "Fp1"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"
    assert frame.index.name == "time"
    assert frame.index.equals(pd.to_datetime(TS[3:7], unit="us", utc=True))
    assert np.isnan(frame["Fp1"].iloc[0])
    assert frame["C4"].tolist() == [103.0, 104.0, 105.0, 106.0]


def test_read_frame_uses_column_names(v1_path):
    with moberg_h5.open(v1_path) as rec:
        frame = rec.read_frame("EEG/qEEG_DSA_Left")
    assert list(frame.columns) == ["0.25", "0.75", "1.25", "1.75"]
    assert frame.shape == (3, 4)


def test_read_frame_rejects_mixed_timestamps(v1_path):
    with moberg_h5.open(v1_path) as rec, pytest.raises(ValueError, match="share a timestamps dataset"):
        rec.read_frame(["EEG/C3", "EEG/HFEEG_C3"])


def test_read_frame_without_pandas(v1_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas", None)
    with moberg_h5.open(v1_path) as rec:
        timestamps, _ = rec.read("EEG/C3")
        with pytest.raises(ImportError, match=r"moberg-h5\[pandas\]"):
            rec.read_frame("EEG/C3")
    assert len(timestamps) == 10


@pytest.mark.parametrize(
    "make_bounds",
    [
        lambda start_ns, end_ns: (np.datetime64(start_ns, "ns"), np.datetime64(end_ns, "ns")),
        lambda start_ns, end_ns: (pd.Timestamp(start_ns, unit="ns", tz="UTC"), pd.Timestamp(end_ns, unit="ns", tz="UTC")),
        lambda start_ns, end_ns: (pd.Timestamp(start_ns, unit="ns"), pd.Timestamp(end_ns, unit="ns").tz_localize("UTC").tz_convert("US/Eastern")),
        # numpy's stubs do not accept multiplied units such as "10ns".
        lambda start_ns, end_ns: (np.datetime64(start_ns // 10, "10ns"), np.datetime64(end_ns // 10, "10ns")),  # ty: ignore[no-matching-overload]
    ],
)
def test_sub_microsecond_bounds_round_up(v1_path, make_bounds):
    start_ns = int(TS[0]) * 1000 + 500
    end_ns = int(TS[1]) * 1000 + 500
    start, end = make_bounds(start_ns, end_ns)
    with moberg_h5.open(v1_path) as rec:
        timestamps, values = rec.read("EEG/C3", start, end)
        gaps = rec.gaps("EEG/C3", end=np.datetime64(int(TS[GAP_AFTER]) * 1000 + 1, "ns"))

    np.testing.assert_array_equal(timestamps, TS[1:2])
    np.testing.assert_array_equal(values, [1.0])
    assert gaps.shape == (1, 2)


def test_whole_microsecond_and_coarse_bounds_are_exact():
    from moberg_h5._time import to_epoch_us

    assert to_epoch_us(np.datetime64(1_700_000_000_123_456_000, "ns")) == 1_700_000_000_123_456
    assert to_epoch_us(np.datetime64(1_700_000_000_123_456_001, "ns")) == 1_700_000_000_123_457
    assert to_epoch_us(np.datetime64(-1_500, "ns")) == -1
    assert to_epoch_us(np.datetime64("2026-11-04T12:00:00", "s")) == 1_793_793_600_000_000
    assert to_epoch_us(pd.Timestamp("2026-11-04T12:00:00.0000005Z")) == 1_793_793_600_000_001  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError):
        to_epoch_us(np.datetime64("NaT", "ns"))
