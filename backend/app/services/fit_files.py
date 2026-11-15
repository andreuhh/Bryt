"""Normalize raw uploads/downloads into plain .fit bytes.

Accepted containers: raw .fit, gzip (.fit.gz — Intervals.icu downloads, Strava bulk export),
zip (Garmin Connect "Export original"). Decompression is size-capped (zip-bomb safe).
"""

import gzip
import io
import zipfile
from typing import IO

GZIP_MAGIC = b"\x1f\x8b"
ZIP_MAGIC = b"PK\x03\x04"


class InvalidFitFileError(ValueError):
    pass


def is_fit(data: bytes) -> bool:
    return len(data) >= 12 and data[0] in (12, 14) and data[8:12] == b".FIT"


def _read_capped(stream: IO[bytes] | gzip.GzipFile, cap: int) -> bytes:
    data = stream.read(cap + 1)
    if len(data) > cap:
        raise InvalidFitFileError(f"Decompressed file exceeds {cap // (1024 * 1024)} MB")
    return data


def extract_fit_bytes(data: bytes, max_bytes: int) -> bytes:
    if data.startswith(GZIP_MAGIC):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                data = _read_capped(gz, max_bytes)
        except (OSError, EOFError) as exc:
            raise InvalidFitFileError("Corrupted gzip archive") from exc
    elif data.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                members = [m for m in zf.infolist() if m.filename.lower().endswith(".fit")]
                if not members:
                    raise InvalidFitFileError("Zip archive contains no .fit file")
                with zf.open(members[0]) as member:
                    data = _read_capped(member, max_bytes)
        except zipfile.BadZipFile as exc:
            raise InvalidFitFileError("Corrupted zip archive") from exc

    if not is_fit(data):
        raise InvalidFitFileError("Not a FIT file (missing .FIT signature)")
    return data
