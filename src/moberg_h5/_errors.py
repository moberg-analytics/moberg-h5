from __future__ import annotations


class MobergH5Error(Exception):
    """Base class for errors raised by moberg_h5."""


class UnsupportedFormatVersion(MobergH5Error):
    """The file declares a format version this reader cannot read."""

    def __init__(self, message: str, version: str) -> None:
        super().__init__(message)
        self.version = version


class FormatError(MobergH5Error):
    """The file does not match the layout it claims to follow."""
