# Changelog

Package releases of moberg-h5. Changes to the HDF5 file layout itself are in
[docs/format-changelog.md](docs/format-changelog.md).

## Unreleased

## 0.1.0 - 2026-11-18

First release.

- `moberg_h5.open` reads connect-client HDF5 files and Moberg Clinical Platform
  HDF5 exports with `format_version` 1.x, and rejects 2.0 and later.
- Files written before format versioning are read best effort, including the
  comma-named datasets written before January 2026.
- `Recording.read` and `Recording.read_frame` read a time range without loading
  the whole dataset. `read_frame` needs the `pandas` extra.
- `Recording.regions`, `Recording.gaps` and `Recording.annotations` return
  microsecond times.
- `Recording.time_range` returns when a signal, or a set of signals, has data,
  ready to pass to `read`. `Recording.summary` lists each signal's range, rows,
  sampling rate and gap count as a DataFrame.
