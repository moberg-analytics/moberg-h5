# moberg-h5

Read HDF5 files exported from Moberg CNS archives by `export-utils` and the
Moberg connect client.

The package lists the measurements in a file, finds each one's timestamps, and
reads a time range without loading the whole dataset. It depends on h5py and
numpy. pandas is optional and only needed for `read_frame`.

## Install

```sh
pip install "moberg-h5 @ git+https://github.com/moberg-analytics/moberg-h5"
# with pandas support
pip install "moberg-h5[pandas] @ git+https://github.com/moberg-analytics/moberg-h5"
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
| No `format_version` (legacy) | Best effort. Timestamps are found by naming convention, including the comma-named datasets that export-utils 0.0.1 wrote before January 2026; region and gap attributes from older files are read. |
| `1.x` | Supported |
| `2.0` and later | Rejected with `UnsupportedFormatVersion`. Install a newer moberg-h5. |

The file layout is documented in the Moberg user manual MCPUM1, "MCP Data
Organization", section 6 (HDF5 Data Structure).

## Development

```sh
uv run pytest
```
