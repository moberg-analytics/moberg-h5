# Moberg HDF5 format

This document describes the HDF5 files that Moberg's connect-client writes when it converts CNS archives, and the HDF5 files exported from the Moberg Clinical Platform (MCP). It covers format version 1.0 and the unversioned layouts written before it. For what changed between versions, see [format-changelog.md](format-changelog.md).

The format builds on the HDF5 layout that Dr. Peter Smielewski and colleagues at the University of Cambridge used in the CENTER-TBI trial, extended to more data types. HDF5 (Hierarchical Data Format version 5) is a self-describing file format from the [HDF Group](https://www.hdfgroup.org/).

## Contents

1. [Terms](#1-terms)
2. [File layout](#2-file-layout)
3. [Timestamps](#3-timestamps)
4. [EEG and HFEEG](#4-eeg-and-hfeeg)
5. [Quantitative EEG](#5-quantitative-eeg)
6. [Waveforms and trends](#6-waveforms-and-trends)
7. [Other measurements](#7-other-measurements)
8. [Annotations](#8-annotations)
9. [Dataset attributes](#9-dataset-attributes)
10. [File attributes](#10-file-attributes)
11. [Continuous regions and gaps](#11-continuous-regions-and-gaps)
12. [Format versions](#12-format-versions)
13. [Legacy layouts](#13-legacy-layouts)
14. [Reading the files](#14-reading-the-files)
15. [Appendix: common measurement names](#appendix-common-measurement-names)

## 1. Terms

- **CNS archive.** The directory the Moberg CNS Monitor records for one monitoring session, named `Patient_<date and time>`, for example `Patient_2021_Nov_28__20_45_15_437001`. Each HDF5 file is named after the archive it came from, with the `.h5` extension.
- **Segment.** A monitor can split a session into `Segment_<time>` subdirectories of fixed length. Consecutive segments usually follow each other without a gap, but a gap between segments is possible.
- **CNS measurement name.** Every measurement in an archive has a five-part name, `<Modality>,<Location>,<Type>,<Representation>,<Source>`, for example `HR,na,Numeric,Float,IntelliVue`. Modality is what was measured (`HR`, `ABP`, `EEG`), location is where (`Left`, `Mean`, or `na` when no location applies), type is how it is stored (`SampleSeries` for regularly sampled signals, `Numeric` and `SparseNumeric` for trend values), representation is the value encoding (`Float`, `Integer`, `Composite`, `CompositeFloat`), and source is the device or program that produced it (`IntelliVue`, `Amp1020`).

## 2. File layout

A file normally holds one CNS archive. Measurements are grouped by type:

| Group | CNS measurements |
|---|---|
| `EEG` | `EEG` and `HFEEG` measurements of type `SampleSeries` with representation `Composite`, split into one dataset per channel; every modality that starts with `qEEG` |
| `Waveforms` | All other `SampleSeries` measurements |
| `Trends` | `Numeric` and `SparseNumeric` measurements |
| `Other` | Everything else, for example `TCD,Left,SBI,Float,Multigon` |
| `Annotations` | Annotations exported from MCP (Section 8) |

Measurements whose names contain `NeonatalParams`, `Impedance` or `Alert` are not exported. A group with no data is not written.

A measurement dataset is named `<Modality>_<Location>`, for example `HR_na` for `HR,na,Numeric,Float,IntelliVue`. EEG channels are the exception (Section 4). Each measurement has a timestamps dataset with the suffix `_Timestamps`, and may have `_ContinuousRegions` and `_Gaps` datasets (Section 11). If two measurements in the same group would get the same name, both are renamed to `<Modality>_<Location>__<Type>__<Representation>__<Source>`, for example `ICP_Mean__Numeric__Float__CaminoCAM02` and `ICP_Mean__Numeric__Float__IntelliVue`. The suffixes follow the renamed name.

Measurement datasets carry attributes that describe the source measurement and point to their timestamps (Section 9). The file carries attributes that identify the format version and the converter (Section 10).

An example file:

```
/                                      file attributes (Section 10)
/EEG/C3, /EEG/C4, ...                  one dataset per EEG channel
/EEG/EEG_Composite_Timestamps          shared by every EEG channel
/EEG/EEG_Composite_ContinuousRegions
/EEG/EEG_Composite_Gaps
/EEG/HFEEG_C3, ...                     one dataset per HFEEG channel
/EEG/HFEEG_Composite_Timestamps
/EEG/qEEG_DSA_C3-P3                    2-D qEEG trend
/EEG/qEEG_DSA_C3-P3_Timestamps
/EEG/qEEG_DSA_C3-P3_ColumnNames
/Waveforms/ABP_na
/Waveforms/ABP_na_Timestamps
/Trends/HR_na
/Trends/HR_na_Timestamps
/Other/TCD_Left
/Other/TCD_Left_Timestamps
```

Some exports put several archives in one file. Each archive then sits under a group named after it, for example `/Patient_2021_Nov_28__20_45_15_437001/EEG/C3`, with the same layout inside. connect-client writes one file per archive.

## 3. Timestamps

Timestamps are 1-D `int64` datasets that count microseconds since 1970-01-01 00:00:00 UTC. A timestamps dataset has one row for each row of the data it describes, in ascending order. The values stay exact as double-precision floats through the year 2255, so MATLAB and R users can convert them to `double` without losing precision.

To find a dataset's timestamps, read its `timestamps` attribute instead of building the name yourself. The attribute holds an absolute path, for example `/EEG/EEG_Composite_Timestamps`. Several datasets can share one timestamps dataset; all channels of one EEG measurement do.

Example values:

```
1511898316337585
1511898316341491
1511898316345397
```

## 4. EEG and HFEEG

Raw EEG is stored as one dataset per channel and one timestamps dataset per EEG measurement. EEG channels use their lead names, such as `EEG/C3`, and share `EEG/EEG_Composite_Timestamps`. HFEEG (high-frequency EEG) channels are in the same group with an `HFEEG_` prefix, such as `EEG/HFEEG_C3`, and share `EEG/HFEEG_Composite_Timestamps`. Each channel dataset has a `sampling_rate` attribute with the nominal rate in Hz.

If an archive holds two EEG measurements of the same modality from different sources, for example two amplifiers, each one's channels are prefixed with its full measurement name (Section 2), such as `EEG/EEG_Composite__SampleSeries__Composite__Amp1020_C3`, so the two sources never share a channel dataset. The same applies to HFEEG: `EEG/HFEEG_Composite__SampleSeries__Composite__Amp1020_C3`. Read the `timestamps` attribute to find each source's timestamps.

Every channel dataset has exactly as many rows as its timestamps dataset, so row *i* of `EEG/C3` and row *i* of `EEG/F4` were sampled at the same time. If the montage changed during the recording, a channel that was not recorded for part of it holds NaN for those rows. A channel added partway through starts with NaN; a channel removed partway through ends with NaN. Channel datasets are floating point so they can hold NaN.

The file does not record the montage's channel order. HDF5 lists datasets alphabetically.

Example values from `EEG/C3`, in microvolts (`units` attribute `uV`):

```
41224.19619178772
140296.19619178772
89219.19619178772
```

## 5. Quantitative EEG

Quantitative EEG (qEEG) metrics computed by MCP are stored as one dataset per metric and location, named `qEEG_<Metric>_<Location>`, for example `qEEG_DSA_C3-P3` or `qEEG_ADR_Left`. Rows are time points and match the 1-D `qEEG_<Metric>_<Location>_Timestamps` dataset.

- A metric with one value per time point (representation `Float`, such as ADR) is a 1-D dataset.
- A metric with several values per time point (representation `CompositeFloat`, such as DSA) is a 2-D dataset whose columns depend on the metric. A `qEEG_<Metric>_<Location>_ColumnNames` dataset lists the column labels as strings, and the data dataset's `column_names_dataset` attribute holds its path.

If the columns of a 2-D qEEG measurement change during the recording, the converter does not write it. It reports an error that names the measurement and the change, and lists the measurement in `failed_basenames` (Section 10).

### Density Spectral Array (DSA)

The DSA is the short-time Fourier transform of the EEG, aggregated into 8-second time bins and 0.5 Hz frequency bins. `qEEG_DSA_<Location>` is an `(N, 40)` matrix: rows are time points and columns are frequency bin centers in Hz. `qEEG_DSA_<Location>_ColumnNames` holds the same centers as strings:

```
0.25, 0.75, 1.25, 1.75, 2.25, 2.75, 3.25, 3.75, 4.25, 4.75,
5.25, 5.75, 6.25, 6.75, 7.25, 7.75, 8.25, 8.75, 9.25, 9.75,
10.25, 10.75, 11.25, 11.75, 12.25, 12.75, 13.25, 13.75, 14.25, 14.75,
15.25, 15.75, 16.25, 16.75, 17.25, 17.75, 18.25, 18.75, 19.25, 19.75
```

## 6. Waveforms and trends

`Waveforms` holds high-frequency signals and `Trends` holds low-frequency values. For example, diastolic, systolic and mean arterial blood pressure are trends, while the arterial blood pressure waveform is in `Waveforms`. Each variable has a data dataset and a timestamps dataset, plus the region and gap datasets in Section 11. Waveform datasets have a `sampling_rate` attribute; trend datasets do not. Use the timestamps for the time of each trend value.

Dataset names come from the label the monitoring device reports, so the same variable can have different names on different devices. Temperature from an IntelliVue monitor is `Temp_na`, but from a GE Solar monitor it is `T1_na`. Blood pressure from a non-invasive cuff is `NBP_Mean`, but from an arterial line it is `ART_Mean`. The appendix lists common names. Which ones a file contains depends on the devices and their configuration during monitoring.

The location part of a name says where or which component was measured: `ABP_Syst` is the systolic component of arterial blood pressure, and `_na` means no location applies, so `ABP_na` is the arterial blood pressure waveform. Location is not consistent across measurements. For EEG it is the electrode; for an arterial line it does not say where the line was placed.

Example values from `Trends/RR_na` and `Trends/RR_na_Timestamps`:

```
39.0    1511898301758546
38.0    1511898302793770
37.0    1511898303828995
```

## 7. Other measurements

Measurements that match none of the `EEG`, `Waveforms` or `Trends` rules are stored in `Other`, with the same dataset names, timestamps, attributes, regions and gaps as any other measurement. An example is the transcranial Doppler measurement `TCD,Left,SBI,Float,Multigon`, stored as `Other/TCD_Left`. Read the `data_type` and `representation` attributes to see what a dataset holds.

Files without a `format_version` put these datasets at the root of the file (Section 13).

## 8. Annotations

Files exported from MCP can include annotations made in MCP. connect-client does not write annotations.

Annotations are one dataset under the `Annotations` group, named after the export time, for example `Annotations/Annotations-12-21-2021 16:53:05`. The dataset is a 2-D array of fixed-length byte strings (1000 bytes each, UTF-8). Each row is one annotation, or one annotation and measurement pair when an annotation applies to several measurements:

| Column | Contents |
|---|---|
| 1 | Annotation group name |
| 2 | Annotation name |
| 3 | Start time, as text, in milliseconds since 1970-01-01 UTC |
| 4 | End time, as text, in milliseconds since 1970-01-01 UTC |
| 5 | Modality of the measurement the annotation applies to (`na` if none) |
| 6 | Location of the measurement the annotation applies to (`na` if none) |

Annotation times are in milliseconds, unlike every other time in the file. Multiply by 1000 to compare them with timestamps.

| Group | Name | Start time | End time | Modality | Location |
|---|---|---|---|---|---|
| Default Session | Custom Annotation | 1640105585000.0 | 1640105585000.0 | ECG | II |
| Default Session | BAD Data | 1640105612000.0 | 1640105612000.0 | EEG | C3 |

The files contain no images.

## 9. Dataset attributes

Every measurement dataset in `EEG`, `Waveforms`, `Trends` and `Other` carries these attributes. All channels of one EEG measurement carry the same values. Timestamps, region, gap and column-name datasets carry no attributes.

| Attribute | Type | Description |
|---|---|---|
| `number_points` | Integer | Sample count the CNS index reports for the source measurement. Use the dataset's length for the number of rows in the file. |
| `start_time` | Integer | Time of the first sample of the source measurement, in microseconds since 1970-01-01 UTC |
| `end_time` | Integer | Time of the last sample of the source measurement, in microseconds since 1970-01-01 UTC |
| `units` | String | Units recorded by the monitor, such as `uV` or `mmHg`. Missing, or the text `None`, when the source recorded none. |
| `label` | String | Full CNS measurement name, such as `HR,na,Numeric,Float,IntelliVue` |
| `location` | String | `<Location>` part of the name |
| `source_device` | String | `<Source>` part of the name |
| `data_type` | String | `<Type>` part of the name, such as `SampleSeries` or `Numeric` |
| `representation` | String | `<Representation>` part of the name, such as `Composite` or `Float` |
| `timestamps` | String | Absolute path of the timestamps dataset for this data |
| `sampling_rate` | Float | Nominal sampling rate in Hz. Written for `SampleSeries` measurements only, and left out when there are too few samples to estimate it. |
| `column_axis` | Integer | 2-D qEEG only: the axis that holds the columns (`1`) |
| `column_names_dataset` | String | 2-D qEEG only: absolute path of the dataset that lists the column labels |
| `column_count` | Integer | 2-D qEEG only: number of columns |

`sampling_rate` is nominal. Gaps and small timing drift make the actual time between samples vary, so use the timestamps for the time of each sample.

## 10. File attributes

The root of the file carries these attributes. All are strings except `failed_basenames`, which is an array of strings.

| Attribute | Example | Description |
|---|---|---|
| `format_version` | `1.0` | Format version, as `MAJOR.MINOR` (Section 12) |
| `converter_name` | `connect-client` | Program that wrote the file |
| `converter_version` | `3.2.0` | Version of that program |
| `export_utils_version` | `3.1.0` | Version of Moberg's HDF5 export library |
| `cns_utils_version` | `1.3.0` | Version of Moberg's CNS decoding library |
| `source_archive` | `Patient_2021_Nov_28__20_45_15_437001` | Name of the CNS archive the file was converted from |
| `created_utc` | `2026-11-04T18:22:01Z` | Time the conversion started, in ISO 8601 UTC |
| `failed_basenames` | `["TCD,Left,SBI,Float,Multigon"]` | Present only when some measurements failed to convert: the CNS names of the measurements left out of the file |

When connect-client cannot convert a measurement, it removes that measurement's datasets, keeps the rest of the file, and lists the measurement in `failed_basenames`. The conversion log and summary give the reason for each. A patient whose measurements all fail gets no file. If `failed_basenames` is absent, no measurement failed. Include the version attributes when you report a problem with a file.

In a file that holds several archives, `source_archive` and `failed_basenames` are set on each `/Patient_*` group instead of the root.

## 11. Continuous regions and gaps

A measurement may have two datasets that describe where the recording has data, `_ContinuousRegions` and `_Gaps`. They sit next to the measurement's timestamps dataset and share its name stem: take the `timestamps` attribute and replace the `_Timestamps` suffix. All channels of an EEG measurement share one pair, for example `EEG/EEG_Composite_ContinuousRegions` and `EEG/EEG_Composite_Gaps`. A measurement exported under its full name uses the full name for every dataset, for example `Trends/ICP_Mean__Numeric__Float__CaminoCAM02_Gaps`.

| Suffix | Type | Each row |
|---|---|---|
| `_ContinuousRegions` | (N, 2) int64 | [first sample time, last sample time] of one run of samples in the CNS index |
| `_Gaps` | (N, 2) int64 | [time of the last sample before the gap, time of the first sample after it] |

Times are in microseconds since 1970-01-01 UTC, like the timestamps.

Continuous regions follow the runs in the archive's index files. A new run can start without a gap, for example at a segment boundary, so two consecutive regions can touch. Use `_Gaps` to find missing data.

A gap is recorded when the time between two runs is longer than the sum of the two runs' sample intervals. Gaps between segments are included. A missing `_ContinuousRegions` or `_Gaps` dataset means the measurement has no regions or no gaps.

These datasets let you find periods with data without scanning the full timestamps dataset.

## 12. Format versions

`format_version` has two numbers, MAJOR and MINOR.

- MAJOR changes when a group, dataset or attribute is renamed, moved or removed, or when its data type, units or meaning changes.
- MINOR changes when something is only added, such as a new attribute or group.

A reader written for one MAJOR version can read any MINOR version of it and ignore what it does not recognize. A reader should refuse a file whose MAJOR version it does not know. moberg-h5 follows these rules. Each version's changes are in [format-changelog.md](format-changelog.md).

The current version is 1.0.

## 13. Legacy layouts

Files without a `format_version` attribute are legacy files, written before format 1.0. Their layout depends on the converter version that wrote them. The dates below are approximate and say when Moberg's builds changed; a site running an older connect-client keeps writing the older layout. moberg-h5 reads all of them.

| How to recognize the file | Written | Layout |
|---|---|---|
| `format_version` present | From November 2026 | Format 1.x, described above |
| No `format_version`; dataset names contain commas, such as `Waveforms/ABP,na,SampleSeries,Integer,IntelliVue`, with timestamps in `<name>,timestamps` | Until January 2026 | [Comma-named layout](#comma-named-layout) |
| `_Timestamps` datasets; `continuous_regions` and `gaps` attributes on each dataset instead of region and gap datasets; HFEEG as one 2-D dataset, `EEG/HFEEG_Composite` | Early January 2026, about one week | Named layout, first version |
| `_Timestamps` datasets; one region and gap pair per EEG channel, such as `EEG/C3_ContinuousRegions`; HFEEG still 2-D | January to May 2026 | Named layout |
| `_Timestamps` datasets; HFEEG split into `EEG/HFEEG_<channel>` datasets; one region and gap pair per EEG measurement (`EEG/EEG_Composite_ContinuousRegions`); `SparseNumeric` measurements at the file root | May to September 2026 | Named layout |
| As above, with `SparseNumeric` measurements in `Trends` | September to November 2026 | Named layout |

### Named layout

Files from January to November 2026 use the group and dataset names described above, with these differences from format 1.0:

- There are no file attributes, `timestamps` attributes or `sampling_rate` attributes. A measurement's timestamps are `<name>_Timestamps` in the same group. EEG channels use `EEG/EEG_Composite_Timestamps` and HFEEG channels `EEG/HFEEG_Composite_Timestamps`, or from May 2026 the full-name form, such as `EEG/EEG_Composite__SampleSeries__Composite__Amp1020_Timestamps`, when two EEG measurements collided.
- Measurements that format 1.0 puts in `Other` are at the root of the file (or the root of each `/Patient_*` group).
- Until May 2026, groups were chosen by searching the measurement name for text: any name containing `EEG` went to `EEG`, then any containing `SampleSeries` to `Waveforms`, then any containing `Numeric` (including `SparseNumeric`) to `Trends`, and everything else to the root. From May 2026, groups follow the rules in Section 2, except for `Other`.
- From May 2026, colliding names in any group are renamed to `<Modality>_<Location>__<Type>__<Representation>__<Source>`, and 2-D qEEG datasets have `_ColumnNames` datasets and the `column_axis`, `column_names_dataset` and `column_count` attributes.
- Two EEG measurements of the same modality wrote into the same channel datasets, so their rows are mixed.
- Gaps cover only gaps inside a segment. A gap between two segments is not listed.
- EEG channel names come from the first segment's montage. If the montage changed between segments, later data can sit under the wrong channel name, or the EEG measurement failed to export.
- A few samples near segment boundaries can be missing, and continuous regions can extend a few milliseconds past the data in the file.
- If any measurement failed, the converter wrote no file for that patient.

### Comma-named layout

Files written before January 2026 store every measurement as one dataset named after its full CNS measurement name, with timestamps in a dataset of the same name followed by `,timestamps`:

- `Waveforms/ABP,na,SampleSeries,Integer,IntelliVue` and `Waveforms/ABP,na,SampleSeries,Integer,IntelliVue,timestamps`
- `Trends/HR,na,Numeric,Float,IntelliVue` and `Trends/HR,na,Numeric,Float,IntelliVue,timestamps`

Groups were chosen by the text search described above, and measurements that matched nothing are at the file root. EEG and HFEEG channels are datasets named after the electrode alone, such as `EEG/C3`, and share their measurement's timestamps, such as `EEG/EEG,Composite,SampleSeries,Composite,Amp1020,timestamps`.

These files also differ in other ways:

- Datasets carry only the `number_points`, `start_time`, `end_time` and `units` attributes. There is no `label`. For EEG channels, the name of the `,timestamps` dataset is the only record of the measurement.
- EEG and HFEEG channels with the same electrode name share one dataset, which holds the EEG rows followed by the HFEEG rows. Such a channel lines up with neither timestamps dataset and cannot be split reliably. Channels whose names appear in only one measurement are unaffected.
- Measurements whose name contains `Float` or `Composite` were stored as 32-bit floats, and those containing `Integer` as 32-bit integers in raw device units. Other measurements were skipped.
- There are no continuous region, gap or annotation datasets.
- A few samples are missing from each measurement near read boundaries. On a 39-hour test archive the loss was 7 to 10 samples per measurement.

## 14. Reading the files

### Python with moberg-h5

moberg-h5 lists the measurements, finds each one's timestamps in format 1.x and legacy files, reads only the time range you ask for, and refuses files whose format version it does not know. It needs h5py and numpy; pandas is optional.

```sh
pip install "moberg-h5[pandas] @ git+https://github.com/moberg-analytics/moberg-h5"
```

```python
from datetime import datetime, timezone

import moberg_h5

HDF5_PATH = "/path/to/Patient_2017_Nov_28__19_45_15_437001.h5"
start = datetime(2017, 11, 29, 12, 0, tzinfo=timezone.utc)
end = datetime(2017, 11, 29, 12, 10, tzinfo=timezone.utc)

with moberg_h5.open(HDF5_PATH) as rec:
    print(rec.format_version, rec.attrs)
    for signal in rec.signals():
        print(signal.path, signal.kind, signal.units, signal.sampling_rate)

    timestamps_us, icp = rec.read("Waveforms/ICP_na", start, end)
    eeg = rec.read_frame(rec.eeg_channels(), start, end)  # pandas DataFrame, UTC index
    gaps = rec.gaps("EEG/C3")
```

### Python with h5py

The files can also be read directly with [h5py](https://docs.h5py.org/). EEG datasets can hold billions of rows, so read slices rather than whole datasets.

```python
import h5py
import matplotlib.pyplot as plt

HDF5_PATH = "/path/to/Patient_2017_Nov_28__19_45_15_437001.h5"
DATASET = "Waveforms/ICP_na"
ROWS = 100_000

with h5py.File(HDF5_PATH, "r") as f:
    f.visit(print)  # every group and dataset in the file

    data = f[DATASET]
    # Format 1.x stores the timestamps path. The fallback finds waveform and trend
    # timestamps in named-layout files; for EEG channels and the comma-named
    # layout see Section 13, or use moberg-h5.
    timestamps = f[data.attrs.get("timestamps", f"{data.name}_Timestamps")]
    values = data[:ROWS]
    times = timestamps[:ROWS].astype("datetime64[us]")  # UTC

plt.figure(figsize=(25, 10), dpi=80)
plt.xlabel("Time (UTC)")
plt.ylabel(DATASET)
plt.plot(times, values)
```

### MATLAB

MATLAB reads HDF5 natively; see [HDF5 Files](https://www.mathworks.com/help/matlab/hdf5-files.html). This format 1.x example reads the first 100,000 rows of one EEG channel and its timestamps:

```matlab
f = 'Patient_2017_Nov_28__19_45_15_437001.h5';
c3 = h5read(f, '/EEG/C3', 1, 100000);
ts = h5read(f, char(h5readatt(f, '/EEG/C3', 'timestamps')), 1, 100000);
t = datetime(double(ts) / 1e6, 'ConvertFrom', 'posixtime', 'TimeZone', 'UTC');
```

Rows that hold NaN belong to channels that were not recorded at that time (Section 4).

### R

R can read the files with [rhdf5](https://bioconductor.org/packages/release/bioc/html/rhdf5.html).

### After export

Moberg Analytics is not responsible for the integrity of data after it leaves Moberg's systems, including overwritten files, file locking and local data loss.

## Appendix: common measurement names

Examples of trend and waveform dataset names by device. A file contains only the measurements its devices recorded.

| Variable | Device | Trend/Waveform | Data Label | Timestamp Label |
|---|---|---|---|---|
| Heart Rate | CARESCAPE | Trend | `HR_na` | `HR_na_Timestamps` |
| | IntelliVue | Trend | `HR_na` | `HR_na_Timestamps` |
| End-tidal CO2 | CARESCAPE | Trend | `EtCO2_na` | `EtCO2_na_Timestamps` |
| | IntelliVue | Trend | `EtCO2_na` | `EtCO2_na_Timestamps` |
| Plethysmography | CARESCAPE | Waveform | `PLETH_na` | `PLETH_na_Timestamps` |
| | IntelliVue | Waveform | `PLETH_na` | `PLETH_na_Timestamps` |
| Carbon Dioxide | IntelliVue | Waveform | `CO2_na` | `CO2_na_Timestamps` |
| ECG | CARESCAPE | Waveform | `ECG_II` | `ECG_II_Timestamps` |
| | IntelliVue | Waveform | `ECG_II` | `ECG_II_Timestamps` |
| Respiratory Rate | CARESCAPE | Trend | `RR_na` | `RR_na_Timestamps` |
| | IntelliVue | Trend | `RR_na` | `RR_na_Timestamps` |
| Respiration Waveform | CARESCAPE | Waveform | `RESP_na` | `RESP_na_Timestamps` |
| | IntelliVue | Waveform | `RESP_na` | `RESP_na_Timestamps` |
| Brain Oxygen | IntelliVue | Waveform | `UVP_na` | `UVP_na_Timestamps` |
| | | Trend | `UVP_Mean` | `UVP_Mean_Timestamps` |
| | Licox | Trend | `PbtO2_na` | `PbtO2_na_Timestamps` |
| Intracranial Pressure | IntelliVue | Waveform | `ICP_na` | `ICP_na_Timestamps` |
| | | Trend | `ICP_Mean` | `ICP_Mean_Timestamps` |
| | | Waveform | `IC1_na` | `IC1_na_Timestamps` |
| | | Trend | `IC1_Mean` | `IC1_Mean_Timestamps` |
| | | Waveform | `IC2_na` | `IC2_na_Timestamps` |
| | | Trend | `IC_Mean` | `IC_Mean_Timestamps` |
| Cerebral Perfusion Pressure | IntelliVue | Trend | `CPP_na` | `CPP_na_Timestamps` |
| Continuous Cardiac Output | Edwards | Trend | `CCI_na` | `CCI_na_Timestamps` |
| | | Trend | `CCO_na` | `CCO_na_Timestamps` |
| PulseOx | CARESCAPE | Trend | `SpO2_na` | `SpO2_na_Timestamps` |
| | IntelliVue | Trend | `SpO2_na` | `SpO2_na_Timestamps` |
| | | Trend | `PR_SpO2` | `PR_SpO2_Timestamps` |
| Water Flow Rate | Arctic Sun | Trend | `FlowRate_na` | `FlowRate_na_Timestamps` |
| Temperature | CARESCAPE | Trend | `T1_na` | `T1_na_Timestamps` |
| | | Trend | `Tbald_na` | `Tbald_na_Timestamps` |
| | IntelliVue | Trend | `Trect_na` | `Trect_na_Timestamps` |
| | | Trend | `Tesop_na` | `Tesop_na_Timestamps` |
| | | Trend | `Temp_na` | `Temp_na_Timestamps` |
| | | Trend | `Tcore_na` | `Tcore_na_Timestamps` |
| | Licox | Trend | `ICT_na` | `ICT_na_Timestamps` |
| | Arctic Sun | Trend | `Tinlet_na` | `Tinlet_na_Timestamps` |
| | | Trend | `Toutlet_na` | `Toutlet_na_Timestamps` |
| | | Trend | `Tpatient1_na` | `Tpatient1_na_Timestamps` |
| | | Trend | `Tpatient2_na` | `Tpatient2_na_Timestamps` |
| | Bowman | Trend | `Tperf_na` | `Tperf_na_Timestamps` |
| Blood Pressure (CARESCAPE — Arterial Line) | CARESCAPE | Waveform | `ART_na` | `ART_na_Timestamps` |
| | | Trend | `ART_Dias` | `ART_Dias_Timestamps` |
| | | Trend | `ART_Syst` | `ART_Syst_Timestamps` |
| | | Trend | `ART_Mean` | `ART_Mean_Timestamps` |
| | | Waveform | `ART1_na` | `ART1_na_Timestamps` |
| | | Trend | `ART1_Dias` | `ART1_Dias_Timestamps` |
| | | Trend | `ART1_Syst` | `ART1_Syst_Timestamps` |
| | | Trend | `ART1_Mean` | `ART1_Mean_Timestamps` |
| | | Waveform | `ART2_na` | `ART2_na_Timestamps` |
| | | Trend | `ART2_Dias` | `ART2_Dias_Timestamps` |
| | | Trend | `ART2_Syst` | `ART2_Syst_Timestamps` |
| | | Trend | `ART2_Mean` | `ART2_Mean_Timestamps` |
| | | Waveform | `ART5_na` | `ART5_na_Timestamps` |
| | | Trend | `ART5_Dias` | `ART5_Dias_Timestamps` |
| | | Trend | `ART5_Syst` | `ART5_Syst_Timestamps` |
| | | Trend | `ART5_Mean` | `ART5_Mean_Timestamps` |
| | | Waveform | `ART6_na` | `ART6_na_Timestamps` |
| | | Trend | `ART6_Dias` | `ART6_Dias_Timestamps` |
| | | Trend | `ART6_Syst` | `ART6_Syst_Timestamps` |
| | | Trend | `ART6_Mean` | `ART6_Mean_Timestamps` |
| Blood Pressure (IntelliVue — Arterial Line) | IntelliVue | Waveform | `ART_na` | `ART_na_Timestamps` |
| | | Trend | `ART_Dias` | `ART_Dias_Timestamps` |
| | | Trend | `ART_Mean` | `ART_Mean_Timestamps` |
| | | Waveform | `Ao_na` | `Ao_na_Timestamps` |
| | | Trend | `Ao_Dias` | `Ao_Dias_Timestamps` |
| | | Trend | `Ao_Mean` | `Ao_Mean_Timestamps` |
| | | Waveform | `ABP_na` | `ABP_na_Timestamps` |
| | | Trend | `ABP_Dias` | `ABP_Dias_Timestamps` |
| | | Trend | `ABP_Mean` | `ABP_Mean_Timestamps` |
| | | Waveform | `P_na` | `P_na_Timestamps` |
| | | Trend | `P_Dias` | `P_Dias_Timestamps` |
| | | Trend | `P_Syst` | `P_Syst_Timestamps` |
| | | Trend | `P_Mean` | `P_Mean_Timestamps` |
| | | Waveform | `P1_na` | `P1_na_Timestamps` |
| | | Trend | `P1_Dias` | `P1_Dias_Timestamps` |
| | | Trend | `P1_Syst` | `P1_Syst_Timestamps` |
| | | Trend | `P1_Mean` | `P1_Mean_Timestamps` |
| | | Waveform | `P2_na` | `P2_na_Timestamps` |
| | | Trend | `P2_Dias` | `P2_Dias_Timestamps` |
| | | Trend | `P2_Syst` | `P2_Syst_Timestamps` |
| | | Trend | `P2_Mean` | `P2_Mean_Timestamps` |
| | | Waveform | `P3_na` | `P3_na_Timestamps` |
| | | Trend | `P3_Dias` | `P3_Dias_Timestamps` |
| | | Trend | `P3_Syst` | `P3_Syst_Timestamps` |
| | | Trend | `P3_Mean` | `P3_Mean_Timestamps` |
| | | Waveform | `P4_na` | `P4_na_Timestamps` |
| | | Trend | `P4_Dias` | `P4_Dias_Timestamps` |
| | | Trend | `P4_Syst` | `P4_Syst_Timestamps` |
| | | Trend | `P4_Mean` | `P4_Mean_Timestamps` |
| | | Waveform | `BAP_na` | `BAP_na_Timestamps` |
| | | Trend | `BAP_Dias` | `BAP_Dias_Timestamps` |
| | | Trend | `BAP_Syst` | `BAP_Syst_Timestamps` |
| | | Trend | `BAP_Mean` | `BAP_Mean_Timestamps` |
| | | Waveform | `FAP_na` | `FAP_na_Timestamps` |
| | | Trend | `FAP_Dias` | `FAP_Dias_Timestamps` |
| | | Trend | `FAP_Syst` | `FAP_Syst_Timestamps` |
| | | Trend | `FAP_Mean` | `FAP_Mean_Timestamps` |
| Blood Pressure (IntelliVue — Noninvasive Cuff) | IntelliVue | Trend | `NBP_Dias` | `NBP_Dias_Timestamps` |
| | | Trend | `NBP_Syst` | `NBP_Syst_Timestamps` |
| | | Trend | `NBP_Mean` | `NBP_Mean_Timestamps` |
| Blood Pressure (CARESCAPE — Noninvasive Cuff) | CARESCAPE | Trend | `NBP_Dias` | `NBP_Dias_Timestamps` |
| | | Trend | `NBP_Syst` | `NBP_Syst_Timestamps` |
| | | Trend | `NBP_Mean` | `NBP_Mean_Timestamps` |
| Central Venous Pressure | IntelliVue | Waveform | `CVP_na` | `CVP_na_Timestamps` |
| | | Trend | `CVP_Mean` | `CVP_Mean_Timestamps` |
| Stroke Volume | Edwards | Trend | `SV_na` | `SV_na_Timestamps` |
| Stroke Volume Index | Edwards | Trend | `SVI_na` | `SVI_na_Timestamps` |
| Stroke Volume Variation | Edwards | Trend | `SVV_na` | `SVV_na_Timestamps` |
| Systemic Vascular Resistance Index | Edwards | Trend | `SVRI_na` | `SVRI_na_Timestamps` |
| Systemic Vascular Resistance | Edwards | Trend | `SVR_na` | `SVR_na_Timestamps` |
| Cerebral Tissue Oxygen Saturation | Edwards | Trend | `A2_Right_Brain` | `A2_Right_Brain_Timestamps` |
| | | Trend | `A1_Left_Brain` | `A1_Left_Brain_Timestamps` |
| | FORESIGHT | Trend | `2_Right_Brain` | `2_Right_Brain_Timestamps` |
| | | Trend | `1_Left_Brain` | `1_Left_Brain_Timestamps` |
