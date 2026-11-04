from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Literal, Sequence, Union

import h5py
import numpy as np

from moberg_h5._errors import FormatError, UnsupportedFormatVersion
from moberg_h5._time import TimeLike, to_epoch_us

if TYPE_CHECKING:
    import pandas as pd

SUPPORTED_MAJOR = 1
DATA_GROUPS = ("EEG", "Waveforms", "Trends", "Other")
ANNOTATIONS_GROUP = "Annotations"
# export-utils 0.0.1 named datasets after the full CNS basename and its timestamps "<basename>,timestamps".
COMMA_TIMESTAMPS_SUFFIX = ",timestamps"
AUX_SUFFIXES = ("_Timestamps", "_ContinuousRegions", "_Gaps", "_ColumnNames", COMMA_TIMESTAMPS_SUFFIX)
EEG_MODALITIES = ("EEG", "HFEEG")
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")

SignalKind = Literal["eeg", "qeeg", "waveform", "trend", "other"]
SIGNAL_KINDS: tuple[SignalKind, ...] = ("eeg", "qeeg", "waveform", "trend", "other")


@dataclass(frozen=True)
class Signal:
    """One measurement dataset and the metadata needed to read it.

    ``path`` is the absolute HDF5 path of the values and ``timestamps_path`` the
    dataset holding their timestamps. ``modality`` and ``channel`` come from the CNS
    basename in ``label``: for ``/EEG/HFEEG_C3`` the modality is ``HFEEG`` and the
    channel ``C3``, and the channel of a source-qualified dataset such as
    ``/EEG/EEG_Composite__SampleSeries__Composite__Amp1020_C3`` is also ``C3``.
    ``units`` is None when the source recorded no units.
    ``sampling_rate`` is the nominal rate in Hz written by format 1.x converters;
    legacy files and trends have none. ``archive`` names the ``Patient_*`` group in
    files that hold several archives, and is None otherwise.
    """

    path: str
    group: str
    name: str
    kind: SignalKind
    timestamps_path: str
    shape: tuple[int, ...]
    dtype: np.dtype
    modality: str | None
    channel: str | None
    units: str | None
    sampling_rate: float | None
    label: str | None
    location: str | None
    source_device: str | None
    data_type: str | None
    representation: str | None
    archive: str | None


@dataclass(frozen=True)
class Annotation:
    """One annotation row. Times are microseconds since the Unix epoch (UTC)."""

    group: str
    text: str
    start_us: int | None
    end_us: int | None
    modality: str
    location: str
    archive: str | None


SignalRef = Union[Signal, str]


class Recording:
    """An open Moberg HDF5 file. Create one with :func:`moberg_h5.open`."""

    def __init__(self, file: h5py.File) -> None:
        self.file = file
        self.format_version = _check_format_version(file)
        self.attrs: dict[str, Any] = {key: _decode(value) for key, value in file.attrs.items()}
        self._archives = _find_archives(file)
        self._signals: list[Signal] | None = None
        self._by_path: dict[str, Signal] = {}
        self._warned_lengths: set[str] = set()

    def __enter__(self) -> Recording:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        version = self.format_version or "legacy"
        return f"<Recording {self.file.filename!r} format={version}>"

    def close(self) -> None:
        self.file.close()

    @property
    def archives(self) -> list[str]:
        """``Patient_*`` group names in a multi-archive file; empty for a single archive."""
        return list(self._archives)

    def signals(self, kind: SignalKind | None = None, archive: str | None = None) -> list[Signal]:
        """List measurement datasets, optionally filtered by kind or archive."""
        if kind is not None and kind not in SIGNAL_KINDS:
            raise ValueError(f"kind must be one of {', '.join(SIGNAL_KINDS)}, got {kind!r}")
        if archive is not None and archive not in self._archives:
            raise KeyError(f"no archive {archive!r} in this file; archives: {self._archives or 'none'}")
        return [
            signal
            for signal in self._all_signals()
            if (kind is None or signal.kind == kind) and (archive is None or signal.archive == archive)
        ]

    def signal(self, path: str) -> Signal:
        """Look up a signal by its HDF5 path, e.g. ``"EEG/C3"`` or ``"/Trends/HR_na"``."""
        self._all_signals()
        normalized = path if path.startswith("/") else f"/{path}"
        try:
            return self._by_path[normalized]
        except KeyError:
            raise KeyError(f"{path!r} is not a measurement dataset in {self.file.filename}") from None

    def eeg_channels(self, modality: str = "EEG", archive: str | None = None) -> list[Signal]:
        """Per-channel EEG datasets for ``modality`` (``"EEG"`` or ``"HFEEG"``)."""
        return [
            signal
            for signal in self.signals(kind="eeg", archive=archive)
            if signal.modality == modality and signal.channel is not None
        ]

    def read(
        self,
        signal: SignalRef,
        start: TimeLike | None = None,
        end: TimeLike | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Read ``(timestamps_us, values)`` for samples with ``start <= t < end``.

        ``start`` and ``end`` accept integer microseconds since the epoch, datetimes
        (naive ones are read as UTC), numpy datetime64 or pandas Timestamps. Only
        the requested rows are read from disk.
        """
        resolved = self._resolve(signal)
        timestamps = self.file[resolved.timestamps_path]
        length = self._common_length([resolved], timestamps)
        lo, hi = _slice_bounds(timestamps, length, start, end)
        return (
            np.asarray(timestamps[lo:hi], dtype=np.int64),
            self.file[resolved.path][lo:hi],
        )

    def read_frame(
        self,
        signals: SignalRef | Sequence[SignalRef],
        start: TimeLike | None = None,
        end: TimeLike | None = None,
    ) -> pd.DataFrame:
        """Read one or more signals into a DataFrame indexed by UTC time.

        Several signals can share one frame when they share a timestamps dataset,
        such as the channels returned by :meth:`eeg_channels`. Needs pandas
        (``pip install "moberg-h5[pandas]"``).
        """
        pd = _require_pandas()
        refs = [signals] if isinstance(signals, (Signal, str)) else list(signals)
        if not refs:
            raise ValueError("read_frame needs at least one signal")
        resolved = [self._resolve(ref) for ref in refs]
        timestamp_paths = sorted({signal.timestamps_path for signal in resolved})
        if len(timestamp_paths) > 1:
            raise ValueError(
                "signals in one frame must share a timestamps dataset; got "
                + ", ".join(timestamp_paths)
            )

        timestamps = self.file[timestamp_paths[0]]
        length = self._common_length(resolved, timestamps)
        lo, hi = _slice_bounds(timestamps, length, start, end)
        index = pd.to_datetime(np.asarray(timestamps[lo:hi], dtype=np.int64), unit="us", utc=True)
        index.name = "time"

        columns: dict[str, np.ndarray] = {}
        for signal in resolved:
            values = self.file[signal.path][lo:hi]
            if values.ndim == 1:
                columns[signal.name] = values
                continue
            names = self._column_names(signal, values.shape[1])
            for column_name, column in zip(names, values.T, strict=True):
                key = column_name if len(resolved) == 1 else f"{signal.name}:{column_name}"
                columns[key] = column
        return pd.DataFrame(columns, index=index)

    def regions(
        self,
        signal: SignalRef,
        start: TimeLike | None = None,
        end: TimeLike | None = None,
    ) -> np.ndarray:
        """Continuous regions as an int64 ``(n, 2)`` array of ``[first_us, last_us]`` rows."""
        return _overlapping(self._auxiliary(signal, "_ContinuousRegions", "continuous_regions"), start, end)

    def gaps(
        self,
        signal: SignalRef,
        start: TimeLike | None = None,
        end: TimeLike | None = None,
    ) -> np.ndarray:
        """Gaps as an int64 ``(n, 2)`` array of ``[last_us_before, first_us_after]`` rows."""
        return _overlapping(self._auxiliary(signal, "_Gaps", "gaps"), start, end)

    def annotations(self, archive: str | None = None) -> list[Annotation]:
        """Annotations exported from Moberg's database, if the file has any."""
        result: list[Annotation] = []
        for name in self._archive_names(archive):
            container = self.file[name] if name else self.file
            group = container.get(ANNOTATIONS_GROUP)
            if not isinstance(group, h5py.Group):
                continue
            for dataset_name in sorted(group):
                dataset = group[dataset_name]
                if not isinstance(dataset, h5py.Dataset):
                    continue
                result.extend(_annotation_rows(dataset, name))
        return result

    def _all_signals(self) -> list[Signal]:
        if self._signals is None:
            self._signals = []
            for archive in self._archive_names(None):
                container = self.file[archive] if archive else self.file
                for group_name in DATA_GROUPS:
                    group = container.get(group_name)
                    if isinstance(group, h5py.Group):
                        self._signals.extend(self._scan(group, group_name, archive))
                self._signals.extend(self._scan(container, "", archive))
            self._by_path = {signal.path: signal for signal in self._signals}
        return self._signals

    def _archive_names(self, archive: str | None) -> list[str | None]:
        if archive is not None:
            if archive not in self._archives:
                raise KeyError(f"no archive {archive!r} in this file; archives: {self._archives or 'none'}")
            return [archive]
        return list(self._archives) if self._archives else [None]

    def _scan(self, group: h5py.Group, group_name: str, archive: str | None) -> Iterable[Signal]:
        for name in group:
            dataset = group.get(name)
            if not isinstance(dataset, h5py.Dataset):
                continue
            timestamps_path = _attr_str(dataset.attrs, "timestamps")
            if timestamps_path is None:
                if name.endswith(AUX_SUFFIXES):
                    continue
                timestamps_path = _legacy_timestamps_path(group, group_name, name, dataset)
                if timestamps_path is None:
                    continue
            elif not isinstance(self.file.get(timestamps_path), h5py.Dataset):
                warnings.warn(
                    f"{dataset.name}: timestamps attribute points to missing dataset {timestamps_path}; skipped",
                    stacklevel=3,
                )
                continue
            yield _make_signal(dataset, group_name, name, timestamps_path, archive)

    def _resolve(self, signal: SignalRef) -> Signal:
        if isinstance(signal, Signal):
            return signal
        return self.signal(signal)

    def _common_length(self, signals: list[Signal], timestamps: h5py.Dataset) -> int:
        length = timestamps.shape[0]
        for signal in signals:
            values_length = self.file[signal.path].shape[0]
            if values_length == length:
                continue
            message = (
                f"{signal.path} has {values_length} rows but {signal.timestamps_path} has "
                f"{timestamps.shape[0]}"
            )
            if self.format_version is not None:
                raise FormatError(message)
            if signal.path not in self._warned_lengths:
                warnings.warn(f"{message}; reading the first {min(length, values_length)} rows", stacklevel=3)
                self._warned_lengths.add(signal.path)
            length = min(length, values_length)
        return length

    def _column_names(self, signal: Signal, count: int) -> list[str]:
        dataset = self.file[signal.path]
        path = _attr_str(dataset.attrs, "column_names_dataset") or f"{signal.path}_ColumnNames"
        names_dataset = self.file.get(path)
        if isinstance(names_dataset, h5py.Dataset) and names_dataset.shape == (count,):
            return [str(_decode(value)) for value in names_dataset[()]]
        return [str(i) for i in range(count)]

    def _auxiliary(self, signal: SignalRef, suffix: str, legacy_attr: str) -> np.ndarray:
        resolved = self._resolve(signal)
        candidates = []
        if resolved.timestamps_path.endswith("_Timestamps"):
            candidates.append(resolved.timestamps_path[: -len("_Timestamps")] + suffix)
        candidates.append(resolved.path + suffix)
        for candidate in candidates:
            dataset = self.file.get(candidate)
            if isinstance(dataset, h5py.Dataset):
                return np.asarray(dataset[()], dtype=np.int64).reshape(-1, 2)

        # Files written before January 2026 stored these arrays as attributes.
        value = self.file[resolved.path].attrs.get(legacy_attr)
        if value is not None and not isinstance(value, (str, bytes)):
            return np.asarray(value, dtype=np.int64).reshape(-1, 2)
        return np.empty((0, 2), dtype=np.int64)


def open(path: str | os.PathLike[str]) -> Recording:  # noqa: A001
    """Open a Moberg HDF5 file for reading.

    Raises :class:`UnsupportedFormatVersion` when the file's major format version
    is newer than this reader understands.
    """
    file = h5py.File(path, "r")
    try:
        return Recording(file)
    except BaseException:
        file.close()
        raise


def _check_format_version(file: h5py.File) -> str | None:
    raw = file.attrs.get("format_version")
    if raw is None:
        return None
    version = str(_decode(raw))
    match = _VERSION_RE.match(version)
    if match is None:
        raise UnsupportedFormatVersion(
            f"{file.filename}: format_version {version!r} is not in MAJOR.MINOR form", version
        )
    if int(match.group(1)) != SUPPORTED_MAJOR:
        from moberg_h5 import __version__

        raise UnsupportedFormatVersion(
            f"{file.filename} uses HDF5 format {version}. moberg-h5 {__version__} reads format "
            f"{SUPPORTED_MAJOR}.x and legacy files without format_version. Install a newer moberg-h5.",
            version,
        )
    return version


def _find_archives(file: h5py.File) -> list[str]:
    if any(name in file for name in DATA_GROUPS):
        return []
    return sorted(
        name for name in file if name.startswith("Patient_") and isinstance(file.get(name), h5py.Group)
    )


def _basename_parts(label: str | None) -> dict[str, str] | None:
    if label is None:
        return None
    parts = label.split(",")
    if len(parts) != 5:
        return None
    return dict(zip(("modality", "location", "data_type", "representation", "source"), parts, strict=True))


def _legacy_timestamps_path(
    group: h5py.Group,
    group_name: str,
    name: str,
    dataset: h5py.Dataset,
) -> str | None:
    """Find timestamps by naming convention, for files without a ``timestamps`` attribute.

    EEG and HFEEG channel datasets share their basename's timestamps. When two
    basenames in a group map to the same name, the writer qualifies both as
    ``<Modality>_<Location>__<Type>__<Representation>__<Source>``. Files from
    export-utils 0.0.1 name datasets ``<basename>`` with ``<basename>,timestamps``.
    """
    if _basename_parts(name) is not None:
        timestamps = group.get(name + COMMA_TIMESTAMPS_SUFFIX)
        return timestamps.name if isinstance(timestamps, h5py.Dataset) else None

    parts = _basename_parts(_attr_str(dataset.attrs, "label"))
    candidates = []
    if parts is not None and _is_channelized(parts):
        stem = f"{parts['modality']}_{parts['location']}"
        candidates += [f"{_qualified_name(parts)}_Timestamps", f"{stem}_Timestamps"]
    elif parts is None and group_name == "EEG" and not name.startswith("qEEG"):
        candidates.append("HFEEG_Composite_Timestamps" if name.startswith("HFEEG_") else "EEG_Composite_Timestamps")
    candidates.append(f"{name}_Timestamps")

    for candidate in candidates:
        timestamps = group.get(candidate)
        if isinstance(timestamps, h5py.Dataset):
            return timestamps.name

    if parts is None and group_name == "EEG":
        return _comma_layout_channel_timestamps(group, dataset)
    return None


def _comma_layout_channel_timestamps(group: h5py.Group, dataset: h5py.Dataset) -> str | None:
    """Match an export-utils 0.0.1 EEG channel to its basename's ``,timestamps`` dataset.

    Those files name channels after the electrode only and record no label, so
    with several EEG basenames (EEG and HFEEG, or two amplifiers) the channel is
    matched by length.
    """
    shared = []
    for candidate_name in group:
        if not candidate_name.endswith(COMMA_TIMESTAMPS_SUFFIX):
            continue
        parts = _basename_parts(candidate_name[: -len(COMMA_TIMESTAMPS_SUFFIX)])
        candidate = group.get(candidate_name)
        if parts is not None and _is_channelized(parts) and isinstance(candidate, h5py.Dataset):
            shared.append(candidate)
    if len(shared) == 1:
        return shared[0].name
    same_length = [candidate for candidate in shared if candidate.shape[:1] == dataset.shape[:1]]
    if len(same_length) == 1:
        return same_length[0].name
    if shared:
        warnings.warn(
            f"{dataset.name}: cannot tell which of {', '.join(c.name for c in shared)} holds its timestamps; skipped",
            stacklevel=4,
        )
    return None


def _qualified_name(parts: dict[str, str]) -> str:
    return (
        f"{parts['modality']}_{parts['location']}__"
        f"{parts['data_type']}__{parts['representation']}__{parts['source']}"
    )


def _is_channelized(parts: dict[str, str]) -> bool:
    return (
        parts["modality"] in EEG_MODALITIES
        and parts["data_type"] == "SampleSeries"
        and parts["representation"] == "Composite"
    )


def _make_signal(
    dataset: h5py.Dataset,
    group_name: str,
    name: str,
    timestamps_path: str,
    archive: str | None,
) -> Signal:
    attrs = dataset.attrs
    label = _attr_str(attrs, "label") or _comma_layout_label(name, timestamps_path)
    parts = _basename_parts(label)
    modality = parts["modality"] if parts else None
    data_type = _attr_str(attrs, "data_type") or (parts["data_type"] if parts else None)
    kind = _classify(group_name, name, modality, data_type)

    channel = None
    if kind == "eeg" and dataset.ndim == 1:
        if modality is None:
            modality = "HFEEG" if name.startswith("HFEEG_") else "EEG"
        channel = _channel_name(name, modality, parts)

    units = _attr_str(attrs, "units")
    sampling_rate = attrs.get("sampling_rate")
    return Signal(
        path=dataset.name,
        group=group_name,
        name=name,
        kind=kind,
        timestamps_path=timestamps_path,
        shape=tuple(dataset.shape),
        dtype=dataset.dtype,
        modality=modality,
        channel=channel,
        units=None if units in (None, "None", "") else units,
        sampling_rate=None if sampling_rate is None else float(sampling_rate),
        label=label,
        location=_attr_str(attrs, "location") or (parts["location"] if parts else None),
        source_device=_attr_str(attrs, "source_device") or (parts["source"] if parts else None),
        data_type=data_type,
        representation=_attr_str(attrs, "representation") or (parts["representation"] if parts else None),
        archive=archive,
    )


def _comma_layout_label(name: str, timestamps_path: str) -> str | None:
    if _basename_parts(name) is not None:
        return name
    timestamps_name = timestamps_path.rsplit("/", 1)[-1]
    if timestamps_name.endswith(COMMA_TIMESTAMPS_SUFFIX):
        return timestamps_name[: -len(COMMA_TIMESTAMPS_SUFFIX)]
    return None


def _channel_name(name: str, modality: str, parts: dict[str, str] | None) -> str:
    prefixes = []
    if parts is not None:
        prefixes.append(f"{_qualified_name(parts)}_")
    if modality != "EEG":
        prefixes.append(f"{modality}_")
    for prefix in prefixes:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _classify(group_name: str, name: str, modality: str | None, data_type: str | None) -> SignalKind:
    if group_name == "Waveforms":
        return "waveform"
    if group_name == "Trends":
        return "trend"
    if group_name == "EEG":
        if (modality or name).startswith("qEEG"):
            return "qeeg"
        if modality is None or modality in EEG_MODALITIES:
            return "eeg"
    # Legacy files wrote unrouted basenames at the root, and before April 2026
    # routed any basename containing "EEG" to the EEG group.
    if group_name != "Other":
        if data_type == "SampleSeries":
            return "waveform"
        if data_type in ("Numeric", "SparseNumeric"):
            return "trend"
    return "other"


def _slice_bounds(
    timestamps: h5py.Dataset,
    length: int,
    start: TimeLike | None,
    end: TimeLike | None,
) -> tuple[int, int]:
    lo = 0 if start is None else _bisect_left(timestamps, to_epoch_us(start), 0, length)
    hi = length if end is None else _bisect_left(timestamps, to_epoch_us(end), lo, length)
    return lo, max(lo, hi)


def _bisect_left(timestamps: h5py.Dataset, target: int, lo: int, hi: int) -> int:
    """First index in [lo, hi) whose timestamp is >= target; reads one value per step."""
    while lo < hi:
        mid = (lo + hi) // 2
        if int(timestamps[mid]) < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _overlapping(rows: np.ndarray, start: TimeLike | None, end: TimeLike | None) -> np.ndarray:
    if start is not None:
        rows = rows[rows[:, 1] >= to_epoch_us(start)]
    if end is not None:
        rows = rows[rows[:, 0] < to_epoch_us(end)]
    return rows


def _annotation_rows(dataset: h5py.Dataset, archive: str | None) -> list[Annotation]:
    rows = dataset[()]
    if rows.size == 0:
        return []
    if rows.ndim != 2 or rows.shape[1] < 6:
        warnings.warn(f"{dataset.name}: expected 6 annotation columns, got shape {rows.shape}; skipped", stacklevel=3)
        return []
    annotations = []
    for row in rows:
        group, text, start, end, modality, location = (str(_decode(cell)) for cell in row[:6])
        annotations.append(
            Annotation(
                group=group,
                text=text,
                start_us=_ms_text_to_us(start),
                end_us=_ms_text_to_us(end),
                modality=modality,
                location=location,
                archive=archive,
            )
        )
    return annotations


def _ms_text_to_us(text: str) -> int | None:
    try:
        return round(float(text) * 1000)
    except ValueError:
        return None


def _decode(value: Any) -> Any:
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.shape == ():
        return _decode(value[()])
    if isinstance(value, np.generic):
        return value.item()
    return value


def _attr_str(attrs: h5py.AttributeManager, key: str) -> str | None:
    value = attrs.get(key)
    if value is None:
        return None
    decoded = _decode(value)
    return decoded if isinstance(decoded, str) else str(decoded)


def _require_pandas() -> Any:
    try:
        import pandas
    except ImportError:
        raise ImportError('read_frame needs pandas; install it with: pip install "moberg-h5[pandas]"') from None
    return pandas
