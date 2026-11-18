from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import h5py
import numpy as np
import pandas as pd
import pytest
from conftest import EEG_TIMESTAMPS, T0

import moberg_h5
from moberg_h5 import TimeRange

TS = EEG_TIMESTAMPS


def test_signal_range_is_a_read_window(v1_path):
    with moberg_h5.open(v1_path) as rec:
        span = rec.time_range("EEG/C3")
        assert span is not None
        timestamps, _ = rec.read("EEG/C3", *span)
        by_datetime, _ = rec.read("EEG/C3", span.start, span.end)

    assert span == (TS[0], TS[-1] + 1)
    np.testing.assert_array_equal(timestamps, TS)
    np.testing.assert_array_equal(by_datetime, TS)


def test_range_ignores_time_attributes(v1_path):
    with h5py.File(v1_path, "r+") as file:
        file["Trends/HR_na"].attrs["start_time"] = int(T0) + 1
        del file["Trends/HR_na"].attrs["end_time"]
    with moberg_h5.open(v1_path) as rec:
        span = rec.time_range("Trends/HR_na")
        assert span is not None
        timestamps, _ = rec.read("Trends/HR_na", *span)
    assert span.start_us == T0
    assert len(timestamps) == 5


def test_channels_sharing_timestamps_read_them_once(v1_path, monkeypatch):
    reads: list[str] = []
    original = h5py.Dataset.__getitem__

    def counting(self, index):
        reads.append(self.name)
        return original(self, index)

    with moberg_h5.open(v1_path) as rec:
        channels = rec.eeg_channels()
        monkeypatch.setattr(h5py.Dataset, "__getitem__", counting)
        spans = {rec.time_range(channel) for channel in channels}

    assert len(channels) == 3 and len(spans) == 1
    assert reads.count("/EEG/EEG_Composite_Timestamps") == 2


def test_empty_signal(v1_path):
    with h5py.File(v1_path, "r+") as file:
        trends = file["Trends"]
        trends.create_dataset("Empty_na_Timestamps", data=np.empty(0, np.int64))
        empty = trends.create_dataset("Empty_na", data=np.empty(0, np.float32))
        empty.attrs["timestamps"] = "/Trends/Empty_na_Timestamps"
    with moberg_h5.open(v1_path) as rec:
        assert rec.time_range("Trends/Empty_na") is None
        assert rec.time_range(kind="trend") == (T0, T0 + 4 * 1_024_000 + 1)
        frame = rec.summary(kind="trend")
    assert frame.loc["/Trends/Empty_na", "rows"] == 0
    assert pd.isna(frame.loc["/Trends/Empty_na", "start"])


def test_file_without_samples_has_no_range(tmp_path):
    path = tmp_path / "empty.h5"
    with h5py.File(path, "w") as file:
        file.attrs["format_version"] = "1.0"
        trends = file.create_group("Trends")
        trends.create_dataset("HR_na_Timestamps", data=np.empty(0, np.int64))
        trends.create_dataset("HR_na", data=np.empty(0, np.float32)).attrs["timestamps"] = "/Trends/HR_na_Timestamps"
    with moberg_h5.open(path) as rec:
        assert rec.time_range() is None


def test_legacy_length_mismatch_ends_at_last_readable_row(legacy_path):
    with h5py.File(legacy_path, "r+") as file:
        file["Waveforms/ECG_II"].resize((7,))
    with moberg_h5.open(legacy_path) as rec:
        with pytest.warns(UserWarning, match="reading the first 7 rows"):
            span = rec.time_range("Waveforms/ECG_II")
        assert span is not None
        timestamps, _ = rec.read("Waveforms/ECG_II", *span)
    assert span == (TS[0], TS[6] + 1)
    assert len(timestamps) == 7


@pytest.mark.parametrize(
    ("fixture", "path", "rows"),
    [
        ("legacy_path", "EEG/C3", 10),
        ("legacy_path", "PbtO2_na", 4),
        ("comma_layout_path", "EEG/C3", 10),
        ("comma_layout_path", "Trends/HR,na,Numeric,Float,Pytest", 5),
    ],
)
def test_legacy_layouts(request, fixture, path, rows):
    with moberg_h5.open(request.getfixturevalue(fixture)) as rec:
        assert rec.time_range(path) == (TS[0], TS[rows - 1] + 1)


def test_file_kind_and_archive_ranges(multi_path):
    with h5py.File(multi_path, "r+") as file:
        shifted = file["Patient_B/Trends/HR_na_Timestamps"][()] + 3_600_000_000
        file["Patient_B/Trends/HR_na_Timestamps"][...] = shifted
    abp_end = T0 + 49 * 8_000 + 1
    with moberg_h5.open(multi_path) as rec:
        assert rec.time_range(archive="Patient_A") == (T0, T0 + 2 * 8_000_000 + 1)
        assert rec.time_range(kind="waveform", archive="Patient_A") == (T0, abp_end)
        assert rec.time_range() == (T0, int(shifted[-1]) + 1)
        with pytest.raises(KeyError):
            rec.time_range(archive="Patient_C")
        with pytest.raises(ValueError, match="not both"):
            rec.time_range("Patient_A/EEG/C3", archive="Patient_A")


def test_time_range_values():
    span = TimeRange(1_700_000_000_000_000, 1_700_000_090_000_001)
    start, end = span
    assert (start, end) == span
    assert span.last_us == 1_700_000_090_000_000
    assert span.duration == timedelta(seconds=90, microseconds=1)
    assert span.start == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert span.end.tzinfo == timezone.utc
    assert repr(span) == "TimeRange(2023-11-14T22:13:20.000000Z -> 2023-11-14T22:14:50.000001Z, 0:01:30.000001)"


def test_summary(v1_path):
    with moberg_h5.open(v1_path) as rec:
        frame = rec.summary()
        row = frame.loc["/EEG/C3"]
        timestamps, _ = rec.read("/EEG/C3", row.start, row.end)
        expected_gaps = {signal.path: len(rec.gaps(signal)) for signal in rec.signals()}

    assert list(frame.columns) == ["archive", "kind", "start", "end", "duration", "rows", "sampling_rate", "gaps"]
    assert frame.index.name == "path"
    assert frame["gaps"].to_dict() == expected_gaps
    assert row.kind == "eeg" and row.rows == 10 and row.sampling_rate == 250.0 and row.gaps == 1
    assert str(frame["start"].dt.tz) == "UTC"
    assert row.duration == pd.Timedelta(microseconds=int(TS[-1] - TS[0] + 1))
    assert np.isnan(frame.loc["/Trends/HR_na", "sampling_rate"])
    np.testing.assert_array_equal(timestamps, TS)


def test_summary_without_pandas(v1_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas", None)
    with moberg_h5.open(v1_path) as rec, pytest.raises(ImportError, match=r"summary needs pandas"):
        rec.summary()
