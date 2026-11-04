from __future__ import annotations

import h5py
import numpy as np
import pytest

import moberg_h5
from conftest import EEG_TIMESTAMPS, T0, eeg_gaps, eeg_regions


def test_legacy_signals_and_kinds(legacy_path):
    with moberg_h5.open(legacy_path) as rec:
        assert rec.format_version is None
        found = {signal.path: signal for signal in rec.signals()}

    assert sorted(found) == ["/EEG/C3", "/EEG/C4", "/EEG/HFEEG_C3", "/PbtO2_na", "/TCD_Left", "/Waveforms/ECG_II"]
    assert found["/PbtO2_na"].kind == "trend"
    assert found["/PbtO2_na"].group == ""
    assert found["/TCD_Left"].kind == "other"
    assert found["/EEG/HFEEG_C3"].channel == "C3"
    assert found["/EEG/C3"].sampling_rate is None


def test_legacy_timestamps_by_naming_convention(legacy_path):
    with moberg_h5.open(legacy_path) as rec:
        assert rec.signal("EEG/C4").timestamps_path == "/EEG/EEG_Composite_Timestamps"
        assert rec.signal("EEG/HFEEG_C3").timestamps_path == "/EEG/HFEEG_Composite_Timestamps"
        assert rec.signal("Waveforms/ECG_II").timestamps_path == "/Waveforms/ECG_II_Timestamps"
        assert rec.signal("PbtO2_na").timestamps_path == "/PbtO2_na_Timestamps"
        timestamps, values = rec.read("EEG/HFEEG_C3", T0 + 5_000, T0 + 8_000)

    np.testing.assert_array_equal(timestamps, T0 + np.array([5_000, 6_000, 7_000]))
    np.testing.assert_array_equal(values, [5, 6, 7])


def test_legacy_per_channel_regions(legacy_path):
    with moberg_h5.open(legacy_path) as rec:
        np.testing.assert_array_equal(rec.regions("EEG/C3"), eeg_regions())
        np.testing.assert_array_equal(rec.gaps("EEG/C3"), eeg_gaps())
        assert rec.gaps("EEG/C4").shape == (0, 2)


def test_legacy_region_attributes(legacy_path):
    with moberg_h5.open(legacy_path) as rec:
        np.testing.assert_array_equal(rec.regions("Waveforms/ECG_II"), eeg_regions())
        np.testing.assert_array_equal(rec.gaps("Waveforms/ECG_II"), eeg_gaps())


def test_legacy_qualified_eeg_timestamps(tmp_path):
    path = tmp_path / "collision.h5"
    with h5py.File(path, "w") as file:
        eeg = file.create_group("EEG")
        for source, offset in (("Amp1020", 0), ("NatusQuantum", 1)):
            basename = f"EEG,Composite,SampleSeries,Composite,{source}"
            eeg.create_dataset(
                f"EEG_Composite__SampleSeries__Composite__{source}_Timestamps",
                data=EEG_TIMESTAMPS + offset,
            )
            channel = eeg.create_dataset(f"{source}_Cz", data=np.arange(10.0))
            channel.attrs["label"] = basename

    with moberg_h5.open(path) as rec:
        assert rec.signal("EEG/NatusQuantum_Cz").timestamps_path == (
            "/EEG/EEG_Composite__SampleSeries__Composite__NatusQuantum_Timestamps"
        )
        timestamps, _ = rec.read("EEG/NatusQuantum_Cz")

    np.testing.assert_array_equal(timestamps, EEG_TIMESTAMPS + 1)


def test_files_without_labels_fall_back_to_composite_timestamps(tmp_path):
    path = tmp_path / "unlabelled.h5"
    with h5py.File(path, "w") as file:
        eeg = file.create_group("EEG")
        eeg.create_dataset("EEG_Composite_Timestamps", data=EEG_TIMESTAMPS)
        eeg.create_dataset("O1", data=np.arange(10.0))
        trends = file.create_group("Trends")
        trends.create_dataset("no_clock", data=np.arange(3.0))

    with moberg_h5.open(path) as rec:
        o1 = rec.signal("EEG/O1")
        paths = [s.path for s in rec.signals()]

    assert (o1.kind, o1.modality, o1.channel) == ("eeg", "EEG", "O1")
    assert "/Trends/no_clock" not in paths


def test_legacy_length_mismatch_warns_and_truncates(legacy_path):
    with h5py.File(legacy_path, "a") as file:
        file["EEG/C4"].resize((8,))

    with moberg_h5.open(legacy_path) as rec:
        with pytest.warns(UserWarning, match="has 8 rows"):
            timestamps, values = rec.read("EEG/C4")

    assert len(timestamps) == len(values) == 8


def test_v1_length_mismatch_raises(v1_path):
    with h5py.File(v1_path, "a") as file:
        file["EEG/C4"].resize((8,))

    with moberg_h5.open(v1_path) as rec:
        with pytest.raises(moberg_h5.FormatError, match="has 8 rows"):
            rec.read("EEG/C4")
