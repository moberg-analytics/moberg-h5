"""Read HDF5 files exported from Moberg CNS archives."""

from importlib.metadata import PackageNotFoundError, version

from moberg_h5._errors import FormatError, MobergH5Error, UnsupportedFormatVersion
from moberg_h5._recording import (
    SUPPORTED_MAJOR,
    Annotation,
    Recording,
    Signal,
    SignalKind,
    open,
)
from moberg_h5._time import TimeRange

try:
    __version__ = version("moberg-h5")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "SUPPORTED_MAJOR",
    "Annotation",
    "FormatError",
    "MobergH5Error",
    "Recording",
    "Signal",
    "SignalKind",
    "TimeRange",
    "UnsupportedFormatVersion",
    "__version__",
    "open",
]
