from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

T0 = 1_700_000_000_000_000
EEG_STEP = 4_000
GAP_AFTER = 5
GAP_US = 1_000_000

# 250 Hz EEG with one 1 s gap after row 5 (a segment boundary).
EEG_TIMESTAMPS = np.array(
    [T0 + i * EEG_STEP + (GAP_US if i > GAP_AFTER else 0) for i in range(10)],
    dtype=np.int64,
)
EEG_BASENAME = "EEG,Composite,SampleSeries,Composite,Amp1020"
HFEEG_BASENAME = "HFEEG,Composite,SampleSeries,Composite,Amp1020"
FP1_FIRST_ROW = 4


def _meta(basename: str, units: str = "uV") -> dict[str, object]:
    _modality, location, data_type, representation, source = basename.split(",")
    return {
        "number_points": 10,
        "start_time": int(EEG_TIMESTAMPS[0]),
        "end_time": int(EEG_TIMESTAMPS[-1]),
        "units": units,
        "label": basename,
        "location": location,
        "source_device": source,
        "data_type": data_type,
        "representation": representation,
    }


def _dataset(group: h5py.Group, name: str, data: np.ndarray, attrs: dict[str, object] | None = None) -> h5py.Dataset:
    maxshape = (None,) if data.ndim == 1 else (None, data.shape[1])
    dataset = group.create_dataset(name, data=data, maxshape=maxshape, compression="gzip")
    for key, value in (attrs or {}).items():
        dataset.attrs[key] = value
    return dataset


def eeg_regions() -> np.ndarray:
    return np.array(
        [[EEG_TIMESTAMPS[0], EEG_TIMESTAMPS[GAP_AFTER]], [EEG_TIMESTAMPS[GAP_AFTER + 1], EEG_TIMESTAMPS[-1]]],
        dtype=np.int64,
    )


def eeg_gaps() -> np.ndarray:
    return np.array([[EEG_TIMESTAMPS[GAP_AFTER], EEG_TIMESTAMPS[GAP_AFTER + 1]]], dtype=np.int64)


def fp1_values() -> np.ndarray:
    values = np.arange(10, dtype=np.float64) * 10.0
    values[:FP1_FIRST_ROW] = np.nan
    return values


def write_v1_archive(root: h5py.Group, prefix: str = "") -> None:
    eeg = root.create_group("EEG")
    _dataset(eeg, "EEG_Composite_Timestamps", EEG_TIMESTAMPS)
    _dataset(eeg, "EEG_Composite_ContinuousRegions", eeg_regions())
    _dataset(eeg, "EEG_Composite_Gaps", eeg_gaps())
    eeg_attrs = {**_meta(EEG_BASENAME), "sampling_rate": 250.0, "timestamps": f"{prefix}/EEG/EEG_Composite_Timestamps"}
    _dataset(eeg, "C3", np.arange(10, dtype=np.float64), eeg_attrs)
    _dataset(eeg, "C4", np.arange(10, dtype=np.float64) + 100, eeg_attrs)
    _dataset(eeg, "Fp1", fp1_values(), eeg_attrs)

    hfeeg_ts = T0 + np.arange(20, dtype=np.int64) * 1_000
    _dataset(eeg, "HFEEG_Composite_Timestamps", hfeeg_ts)
    hfeeg_attrs = {
        **_meta(HFEEG_BASENAME),
        "sampling_rate": 1000.0,
        "timestamps": f"{prefix}/EEG/HFEEG_Composite_Timestamps",
    }
    _dataset(eeg, "HFEEG_C3", np.arange(20, dtype=np.float32), hfeeg_attrs)

    dsa_ts = T0 + np.arange(3, dtype=np.int64) * 8_000_000
    _dataset(eeg, "qEEG_DSA_Left_Timestamps", dsa_ts)
    string_type = h5py.string_dtype(encoding="utf-8")
    eeg.create_dataset("qEEG_DSA_Left_ColumnNames", data=np.array(["0.25", "0.75", "1.25", "1.75"], dtype=object), dtype=string_type)
    _dataset(
        eeg,
        "qEEG_DSA_Left",
        np.arange(12, dtype=np.float32).reshape(3, 4),
        {
            **_meta("qEEG_DSA,Left,SampleSeries,CompositeFloat,Persyst", units="dB"),
            "sampling_rate": 0.125,
            "column_axis": 1,
            "column_names_dataset": f"{prefix}/EEG/qEEG_DSA_Left_ColumnNames",
            "column_count": 4,
            "timestamps": f"{prefix}/EEG/qEEG_DSA_Left_Timestamps",
        },
    )

    waves = root.create_group("Waveforms")
    abp_ts = T0 + np.arange(50, dtype=np.int64) * 8_000
    _dataset(waves, "ABP_na_Timestamps", abp_ts)
    _dataset(
        waves,
        "ABP_na",
        np.linspace(80, 120, 50),
        {**_meta("ABP,na,SampleSeries,Float,IntelliVue", units="mmHg"), "sampling_rate": 125.0, "timestamps": f"{prefix}/Waveforms/ABP_na_Timestamps"},
    )

    trends = root.create_group("Trends")
    hr_ts = T0 + np.arange(5, dtype=np.int64) * 1_024_000
    _dataset(trends, "HR_na_Timestamps", hr_ts)
    _dataset(
        trends,
        "HR_na",
        np.array([70, 71, 72, 73, 74], dtype=np.float32),
        {**_meta("HR,na,Numeric,Float,IntelliVue", units="None"), "timestamps": f"{prefix}/Trends/HR_na_Timestamps"},
    )
    for source in ("CaminoCAM02", "IntelliVue"):
        name = f"ICP_Mean__Numeric__Float__{source}"
        _dataset(trends, f"{name}_Timestamps", hr_ts)
        _dataset(
            trends,
            name,
            np.full(5, 10.0 if source == "IntelliVue" else 12.0),
            {**_meta(f"ICP,Mean,Numeric,Float,{source}", units="mmHg"), "timestamps": f"{prefix}/Trends/{name}_Timestamps"},
        )

    other = root.create_group("Other")
    _dataset(other, "TCD_shared_clock", hr_ts)
    _dataset(
        other,
        "TCD_Left",
        np.array([1, 2, 3, 4, 5], dtype=np.float32),
        {**_meta("TCD,Left,SBI,Float,Multigon", units="cm/s"), "timestamps": f"{prefix}/Other/TCD_shared_clock"},
    )

    annotations = root.create_group("Annotations")
    rows = np.array(
        [
            ["Default Session", "Seizure onset", "1700000000004.0", "1700000000020.5", "EEG", "C3"],
            ["Default Session", "Artifact", "1700000001000.0", "1700000001000.0", "na", "na"],
        ]
    ).astype("S1000")
    annotations.create_dataset("Annotations-11-04-2026 12:00:00", data=rows)


def write_root_attrs(file: h5py.File, version: str | bytes = "1.0", source_archive: str | None = "Patient_2026_Nov_04__10_00_00_000000") -> None:
    file.attrs["format_version"] = version
    file.attrs["converter_name"] = "connect-client"
    file.attrs["converter_version"] = "3.2.0"
    file.attrs["export_utils_version"] = "3.1.0"
    file.attrs["cns_utils_version"] = "1.3.0"
    file.attrs["created_utc"] = "2026-11-04T18:22:01Z"
    if source_archive is not None:
        file.attrs["source_archive"] = source_archive


@pytest.fixture
def v1_path(tmp_path: Path) -> Path:
    path = tmp_path / "v1.h5"
    with h5py.File(path, "w") as file:
        write_root_attrs(file)
        write_v1_archive(file)
    return path


@pytest.fixture
def multi_path(tmp_path: Path) -> Path:
    path = tmp_path / "multi.h5"
    with h5py.File(path, "w") as file:
        write_root_attrs(file, source_archive=None)
        for name in ("Patient_A", "Patient_B"):
            group = file.create_group(name)
            group.attrs["source_archive"] = name
            write_v1_archive(group, prefix=f"/{name}")
    return path


@pytest.fixture
def legacy_path(tmp_path: Path) -> Path:
    """A file shaped like converter output between May and September 2026,
    with older pieces mixed in: per-channel regions (January to May 2026) and
    region/gap attributes (early January 2026)."""
    path = tmp_path / "legacy.h5"
    with h5py.File(path, "w") as file:
        eeg = file.create_group("EEG")
        _dataset(eeg, "EEG_Composite_Timestamps", EEG_TIMESTAMPS)
        _dataset(eeg, "C3", np.arange(10, dtype=np.float64), _meta(EEG_BASENAME))
        _dataset(eeg, "C4", np.arange(10, dtype=np.float64) + 100, _meta(EEG_BASENAME))
        _dataset(eeg, "C3_ContinuousRegions", eeg_regions())
        _dataset(eeg, "C3_Gaps", eeg_gaps())
        _dataset(eeg, "HFEEG_Composite_Timestamps", T0 + np.arange(20, dtype=np.int64) * 1_000)
        _dataset(eeg, "HFEEG_C3", np.arange(20, dtype=np.float32), _meta(HFEEG_BASENAME))

        waves = file.create_group("Waveforms")
        _dataset(waves, "ECG_II_Timestamps", EEG_TIMESTAMPS)
        ecg = _dataset(waves, "ECG_II", np.linspace(0, 1, 10), _meta("ECG,II,SampleSeries,Float,IntelliVue", units="mV"))
        ecg.attrs["continuous_regions"] = eeg_regions()
        ecg.attrs["gaps"] = eeg_gaps()

        _dataset(file, "PbtO2_na_Timestamps", EEG_TIMESTAMPS[:4])
        _dataset(file, "PbtO2_na", np.array([20, 21, 22, 23], dtype=np.float32), _meta("PbtO2,na,SparseNumeric,Float,Licox", units="mmHg"))
        _dataset(file, "TCD_Left_Timestamps", EEG_TIMESTAMPS[:3])
        _dataset(file, "TCD_Left", np.array([1, 2, 3], dtype=np.float32), _meta("TCD,Left,SBI,Float,Multigon", units="cm/s"))
    return path


def _comma_dataset(group: h5py.Group, name: str, data: np.ndarray, units: str | None = None) -> None:
    dataset = group.create_dataset(name, data.shape, data.dtype, data, maxshape=(None,))
    if units is not None:
        dataset.attrs["number_points"] = data.shape[0]
        dataset.attrs["start_time"] = 0
        dataset.attrs["end_time"] = 0
        dataset.attrs["units"] = units


@pytest.fixture
def comma_layout_path(tmp_path: Path) -> Path:
    """A file shaped like converter output from before January 2026, checked against
    that converter run on a synthetic archive: datasets named after the
    full CNS basename, timestamps in "<basename>,timestamps", EEG channels named after
    the electrode, and only number_points, start_time, end_time and units attributes."""
    path = tmp_path / "comma.h5"
    with h5py.File(path, "w") as file:
        eeg = file.create_group("EEG")
        for lead in ("C3", "C4", "Cz"):
            _comma_dataset(eeg, lead, np.arange(10, dtype=np.float32), units="uV")
        _comma_dataset(eeg, "EEG,Composite,SampleSeries,Composite,Pytest,timestamps", EEG_TIMESTAMPS)

        waves = file.create_group("Waveforms")
        _comma_dataset(waves, "ABP,na,SampleSeries,Float,Pytest", np.linspace(80, 120, 10).astype(np.float32), units="mmHg")
        _comma_dataset(waves, "ABP,na,SampleSeries,Float,Pytest,timestamps", EEG_TIMESTAMPS)

        trends = file.create_group("Trends")
        _comma_dataset(trends, "HR,na,Numeric,Float,Pytest", np.arange(5, dtype=np.float32) + 60, units="bpm")
        _comma_dataset(trends, "HR,na,Numeric,Float,Pytest,timestamps", EEG_TIMESTAMPS[:5])
        _comma_dataset(trends, "PbtO2,na,SparseNumeric,Float,Pytest", np.arange(3, dtype=np.float32) + 20, units="mmHg")
        _comma_dataset(trends, "PbtO2,na,SparseNumeric,Float,Pytest,timestamps", EEG_TIMESTAMPS[:3])

        _comma_dataset(file, "TCD,Left,SBI,Float,Multigon", np.arange(3, dtype=np.float32), units="cm/s")
        _comma_dataset(file, "TCD,Left,SBI,Float,Multigon,timestamps", EEG_TIMESTAMPS[:3])
    return path
