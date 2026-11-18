# moberg-h5

Read the HDF5 files that Moberg's connect-client writes from CNS archives, and
HDF5 exports from the Moberg Clinical Platform.

The package lists the measurements in a file, finds each one's timestamps, and
reads a time range without loading the whole dataset. It depends on h5py and
numpy. pandas is optional and only needed for `read_frame`.

Documentation:

- [HDF5 format](https://github.com/moberg-analytics/moberg-h5/blob/main/docs/hdf5-format.md): groups, dataset names, timestamps,
  attributes, regions and gaps, and the layouts written before format versioning.
- [Format changelog](https://github.com/moberg-analytics/moberg-h5/blob/main/docs/format-changelog.md): what changed in each
  `format_version`.

## Install

```sh
pip install moberg-h5
# with pandas support
pip install "moberg-h5[pandas]"
```

Python 3.10 or newer.

## Example

```python
from datetime import datetime, timezone

import moberg_h5

with moberg_h5.open("Patient_2026_Nov_04__10_00_00_000000.h5") as rec:
    print(rec.format_version, rec.attrs.get("converter_name"))
    for signal in rec.signals(kind="trend"):
        print(signal.path, signal.units)

    start = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 11, 4, 12, 10, tzinfo=timezone.utc)
    timestamps_us, icp = rec.read("Trends/ICP_Mean", start, end)
    eeg = rec.read_frame(rec.eeg_channels(), start, end)  # DataFrame, UTC index
    gaps = rec.gaps("EEG/C3", start, end)
```

## Choosing a time window

`time_range` returns the first sample time and the time 1 µs after the last
sample, so it can go straight into `read`, which reads `start <= t < end`:

```python
from datetime import timedelta

with moberg_h5.open(path) as rec:
    print(rec.time_range())                       # whole file
    print(rec.summary(kind="trend"))              # one row per signal
    span = rec.time_range("Trends/ICP_Mean")
    t, icp = rec.read("Trends/ICP_Mean", *span)   # every row
    t, icp = rec.read("Trends/ICP_Mean", span.start, span.start + timedelta(minutes=10))
```

A `TimeRange` unpacks to `(start_us, end_us)` in integer microseconds. `start`
and `end` give the same bounds as UTC datetimes; `last_us` and `duration` are
also available. In a file with several archives the whole-file range includes
the time between archives, so use `archive=`, `summary()` or `regions()` to find
where there is data.

The range comes from the first and last timestamps. The `start_time` and
`end_time` dataset attributes can be up to 1 µs late, which can drop the first
sample when used as `start`.

## API

| Call | Returns |
|---|---|
| `moberg_h5.open(path)` | `Recording`, usable as a context manager |
| `rec.format_version` | `"1.0"`, or `None` for files written before format versioning |
| `rec.attrs` | Root attributes: converter name and version, source archive, creation time |
| `rec.archives` | `Patient_*` group names in a file that holds several archives |
| `rec.signals(kind=None, archive=None)` | `Signal` list; kinds are `eeg`, `qeeg`, `waveform`, `trend`, `other` |
| `rec.signal(path)` | One `Signal` by HDF5 path |
| `rec.eeg_channels(modality="EEG")` | Per-channel EEG datasets; pass `"HFEEG"` for high-frequency EEG |
| `rec.read(signal, start=None, end=None)` | `(timestamps_us, values)` for `start <= t < end` |
| `rec.read_frame(signals, start=None, end=None)` | pandas DataFrame indexed by UTC time |
| `rec.time_range(signal=None, kind=None, archive=None)` | `TimeRange` from the first sample to 1 µs after the last, for one signal or all matching signals; `None` without samples |
| `rec.summary(kind=None, archive=None)` | pandas DataFrame, one row per signal: archive, kind, start, end, duration, rows, sampling rate, gap count |
| `rec.regions(signal)`, `rec.gaps(signal)` | int64 `(n, 2)` arrays of microsecond times |
| `rec.annotations()` | `Annotation` list with microsecond start and end times |

Times passed to `read`, `read_frame`, `regions` and `gaps` can be integer
microseconds since the Unix epoch, `datetime` (naive values are read as UTC),
`numpy.datetime64` or `pandas.Timestamp`. Timestamps come back as int64
microseconds since the Unix epoch, UTC.

A `Signal` carries the dataset path, its timestamps path, `units`,
`sampling_rate` (Hz, format 1.x only), the CNS `label`, `location`,
`source_device`, `data_type` and `representation`, and for EEG the `modality`
and `channel`.

EEG channels that were not recorded for part of a session (a montage change)
hold NaN for those rows, so every channel lines up with the shared timestamps.

## Format versions

Files written by newer converters carry a root attribute `format_version` in
`MAJOR.MINOR` form. MINOR goes up when something is added; MAJOR goes up when a
group, dataset or attribute is renamed, moved, removed or changes meaning.

| File | Support |
|---|---|
| No `format_version` (legacy) | Best effort. Timestamps are found by naming convention, including the comma-named datasets written before January 2026; region and gap attributes from older files are read. |
| `1.x` | Supported |
| `2.0` and later | Rejected with `UnsupportedFormatVersion`. Install a newer moberg-h5. |

The layout is described in
[docs/hdf5-format.md](https://github.com/moberg-analytics/moberg-h5/blob/main/docs/hdf5-format.md)
and the changes in each version in
[docs/format-changelog.md](https://github.com/moberg-analytics/moberg-h5/blob/main/docs/format-changelog.md).

## Development

```sh
uv run pytest
```

Package releases are listed in
[CHANGELOG.md](https://github.com/moberg-analytics/moberg-h5/blob/main/CHANGELOG.md).
Pushing a `vX.Y.Z` tag publishes to PyPI after a maintainer approves the
deployment; `.agents/skills/release/SKILL.md` has the steps.

## License

MIT. See [LICENSE](https://github.com/moberg-analytics/moberg-h5/blob/main/LICENSE).
