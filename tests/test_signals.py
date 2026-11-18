from __future__ import annotations

import h5py
import numpy as np
import pytest
from conftest import EEG_TIMESTAMPS, T0, eeg_gaps, eeg_regions, write_root_attrs

import moberg_h5


def test_lists_every_measurement_and_skips_auxiliary_datasets(v1_path):
    with moberg_h5.open(v1_path) as rec:
        paths = sorted(signal.path for signal in rec.signals())

    assert paths == [
        "/EEG/C3",
        "/EEG/C4",
        "/EEG/Fp1",
        "/EEG/HFEEG_C3",
        "/EEG/qEEG_DSA_Left",
        "/Other/TCD_Left",
        "/Trends/HR_na",
        "/Trends/ICP_Mean__Numeric__Float__CaminoCAM02",
        "/Trends/ICP_Mean__Numeric__Float__IntelliVue",
        "/Waveforms/ABP_na",
    ]


def test_signal_metadata(v1_path):
    with moberg_h5.open(v1_path) as rec:
        c3 = rec.signal("EEG/C3")
        hfeeg = rec.signal("/EEG/HFEEG_C3")
        hr = rec.signal("Trends/HR_na")
        dsa = rec.signal("EEG/qEEG_DSA_Left")
        tcd = rec.signal("Other/TCD_Left")

    assert (c3.kind, c3.modality, c3.channel, c3.group) == ("eeg", "EEG", "C3", "EEG")
    assert c3.units == "uV"
    assert c3.sampling_rate == 250.0
    assert c3.label == "EEG,Composite,SampleSeries,Composite,Amp1020"
    assert c3.source_device == "Amp1020"
    assert c3.shape == (10,)

    assert (hfeeg.kind, hfeeg.modality, hfeeg.channel) == ("eeg", "HFEEG", "C3")
    assert hfeeg.sampling_rate == 1000.0

    assert hr.kind == "trend"
    assert hr.units is None
    assert hr.sampling_rate is None

    assert dsa.kind == "qeeg"
    assert dsa.channel is None
    assert dsa.shape == (3, 4)

    assert tcd.kind == "other"
    assert tcd.group == "Other"


def test_filters(v1_path):
    with moberg_h5.open(v1_path) as rec:
        assert [s.name for s in rec.signals(kind="waveform")] == ["ABP_na"]
        assert [s.channel for s in rec.eeg_channels()] == ["C3", "C4", "Fp1"]
        assert [s.channel for s in rec.eeg_channels("HFEEG")] == ["C3"]
        with pytest.raises(ValueError):
            rec.signals(kind="eegs")
        with pytest.raises(KeyError):
            rec.signal("EEG/EEG_Composite_Timestamps")


def test_root_attributes(v1_path):
    with moberg_h5.open(v1_path) as rec:
        assert rec.format_version == "1.0"
        assert rec.attrs["converter_name"] == "connect-client"
        assert rec.attrs["source_archive"] == "Patient_2026_Nov_04__10_00_00_000000"
        assert rec.archives == []


def test_timestamps_attribute_wins_over_naming_convention(v1_path):
    with moberg_h5.open(v1_path) as rec:
        tcd = rec.signal("Other/TCD_Left")
        c3 = rec.signal("EEG/C3")

    assert tcd.timestamps_path == "/Other/TCD_shared_clock"
    assert c3.timestamps_path == "/EEG/EEG_Composite_Timestamps"


def test_missing_timestamps_target_is_skipped_with_warning(v1_path):
    with h5py.File(v1_path, "a") as file:
        file["Trends/HR_na"].attrs["timestamps"] = "/Trends/nope"

    with moberg_h5.open(v1_path) as rec:
        with pytest.warns(UserWarning, match="missing dataset /Trends/nope"):
            paths = [signal.path for signal in rec.signals()]

    assert "/Trends/HR_na" not in paths


def test_regions_and_gaps_are_shared_by_eeg_channels(v1_path):
    with moberg_h5.open(v1_path) as rec:
        np.testing.assert_array_equal(rec.regions("EEG/C3"), eeg_regions())
        np.testing.assert_array_equal(rec.gaps("EEG/Fp1"), eeg_gaps())
        assert rec.gaps("Trends/HR_na").shape == (0, 2)


def test_gaps_filtered_by_time(v1_path):
    with moberg_h5.open(v1_path) as rec:
        before = rec.gaps("EEG/C3", end=int(EEG_TIMESTAMPS[5]))
        after = rec.gaps("EEG/C3", start=int(EEG_TIMESTAMPS[6]))
        overlapping = rec.gaps("EEG/C3", start=int(EEG_TIMESTAMPS[5]) + 1, end=int(EEG_TIMESTAMPS[6]))

    assert before.shape == (0, 2)
    np.testing.assert_array_equal(after, eeg_gaps())
    np.testing.assert_array_equal(overlapping, eeg_gaps())


def test_annotations(v1_path):
    with moberg_h5.open(v1_path) as rec:
        annotations = rec.annotations()

    assert [a.text for a in annotations] == ["Seizure onset", "Artifact"]
    first = annotations[0]
    assert first.group == "Default Session"
    assert first.start_us == T0 + 4_000
    assert first.end_us == T0 + 20_500
    assert (first.modality, first.location) == ("EEG", "C3")


def test_multi_archive_file(multi_path):
    with moberg_h5.open(multi_path) as rec:
        assert rec.archives == ["Patient_A", "Patient_B"]
        channels = rec.eeg_channels(archive="Patient_B")
        assert [s.path for s in channels] == ["/Patient_B/EEG/C3", "/Patient_B/EEG/C4", "/Patient_B/EEG/Fp1"]
        assert channels[0].timestamps_path == "/Patient_B/EEG/EEG_Composite_Timestamps"
        assert {s.archive for s in rec.signals()} == {"Patient_A", "Patient_B"}
        assert len(rec.annotations()) == 4
        timestamps, _ = rec.read("Patient_A/EEG/C3")
        np.testing.assert_array_equal(timestamps, EEG_TIMESTAMPS)
        with pytest.raises(KeyError):
            rec.signals(archive="Patient_C")


def test_source_qualified_channels(tmp_path):
    path = tmp_path / "two_amplifiers.h5"
    with h5py.File(path, "w") as file:
        write_root_attrs(file)
        eeg = file.create_group("EEG")
        for modality, source in (("EEG", "Amp1020"), ("EEG", "Pytest"), ("HFEEG", "Pytest"), ("HFEEG", "Amp1020")):
            basename = f"{modality},Composite,SampleSeries,Composite,{source}"
            qualified = f"{modality}_Composite__SampleSeries__Composite__{source}"
            eeg.create_dataset(f"{qualified}_Timestamps", data=EEG_TIMESTAMPS)
            channel = eeg.create_dataset(f"{qualified}_C3", data=np.arange(10.0))
            channel.attrs["label"] = basename
            channel.attrs["timestamps"] = f"/EEG/{qualified}_Timestamps"

    with moberg_h5.open(path) as rec:
        eeg_channels = rec.eeg_channels()
        hfeeg_channels = rec.eeg_channels("HFEEG")

    assert [(s.name, s.channel, s.source_device) for s in eeg_channels] == [
        ("EEG_Composite__SampleSeries__Composite__Amp1020_C3", "C3", "Amp1020"),
        ("EEG_Composite__SampleSeries__Composite__Pytest_C3", "C3", "Pytest"),
    ]
    assert [s.channel for s in hfeeg_channels] == ["C3", "C3"]
    assert hfeeg_channels[0].path == "/EEG/HFEEG_Composite__SampleSeries__Composite__Amp1020_C3"
