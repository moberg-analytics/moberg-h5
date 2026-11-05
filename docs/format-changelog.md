# HDF5 format changelog

Each HDF5 file written by connect-client records its layout version in the root attribute `format_version`, as `MAJOR.MINOR`. This file lists what changed in each version. The layout itself is described in [hdf5-format.md](hdf5-format.md).

## Versioning rules

- MAJOR goes up for a breaking change: a group, dataset or attribute is renamed, moved or removed, or its data type, units or meaning changes.
- MINOR goes up when something is only added, such as a new attribute or group. Files of a new MINOR version read correctly with code written for an earlier MINOR of the same MAJOR.
- A reader accepts any MINOR version of a MAJOR version it knows, ignores what it does not recognize, and refuses a file with an unknown MAJOR version. moberg-h5 follows these rules and raises `UnsupportedFormatVersion` for an unknown MAJOR.

Files without `format_version` were written before versioning began. Section 13 of [hdf5-format.md](hdf5-format.md) describes those layouts and how to tell them apart.

## 1.0

First versioned format, written by connect-client releases from November 2026. Changes from the last unversioned layout (September to November 2026):

### Added

- File attributes on the root: `format_version`, `converter_name`, `converter_version`, `export_utils_version`, `cns_utils_version`, `source_archive` and `created_utc`. In a file that holds several archives, `source_archive` is set on each `/Patient_*` group.
- `failed_basenames` file attribute. When some measurements fail to convert, connect-client now keeps the file with the measurements that did convert and lists the failed ones here. Before, any failed measurement meant no file for that patient.
- `timestamps` attribute on every measurement dataset: the absolute path of its timestamps dataset.
- `sampling_rate` attribute (nominal Hz) on `SampleSeries` measurement datasets: EEG and HFEEG channels, waveforms and qEEG.

### Changed

- Measurements that match no other group now go in a new `Other` group instead of the file root. For example, `/TCD_Left` is now `/Other/TCD_Left`.
- EEG and HFEEG channels: every channel dataset now has exactly as many rows as its timestamps dataset. When the montage changes during a recording, a channel holds NaN for the rows where it was not recorded. Before, every channel was named from the first segment's montage, so after a montage change data could sit under the wrong channel name, or the EEG measurement failed to export.
- Two EEG (or HFEEG) measurements from different sources in one archive now get separate channel datasets prefixed with the full measurement name, such as `EEG/EEG_Composite__SampleSeries__Composite__Amp1020_C3`. Before, both sources wrote into the same channel datasets and their rows were mixed.
- `_Gaps` datasets now include gaps between segments of a segmented archive. Before, they listed only gaps inside a segment.
- Samples recorded just past the start of the next segment are no longer dropped, and continuous regions no longer extend past the data in the file.
- A 2-D qEEG measurement whose columns change during the recording is no longer written. The converter reports the change and lists the measurement in `failed_basenames`.

### Unchanged

Group names other than `Other`, dataset names and suffixes, timestamps (int64 microseconds since 1970-01-01 UTC), the existing dataset attributes, region and gap datasets, column-name datasets and annotations.
