"""Minimal FIT encoder for tests: builds valid, CRC-checked activity files.

Also usable from the CLI to produce a sample file for manual upload testing:
    python -m tests.fit_builder sample.fit
"""

import struct
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from fitparse.records import Crc

FIT_EPOCH = 631065600  # 1989-12-31T00:00:00Z

ENUM, UINT8, UINT16, UINT32 = (0x00, 1, "B"), (0x02, 1, "B"), (0x84, 2, "H"), (0x86, 4, "I")

SPORT_RUNNING, SPORT_CYCLING = 1, 2
SUB_SPORT = {"treadmill": 1, "street": 2, "trail": 3, "track": 4}


@dataclass
class Sample:
    heart_rate: int | None
    cadence_spm: float | None  # steps/min; encoded as strides/min like Garmin
    speed_mps: float
    altitude_m: float
    distance_m: float
    gct_ms: float | None


def _fit_ts(dt: datetime) -> int:
    return int(dt.timestamp()) - FIT_EPOCH


class _Writer:
    def __init__(self) -> None:
        self.body = bytearray()

    def define(
        self, local: int, global_num: int, fields: list[tuple[int, tuple[int, int, str]]]
    ) -> None:
        self.body += struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(fields))
        for num, (base, size, _) in fields:
            self.body += struct.pack("<BBB", num, size, base)

    def data(
        self, local: int, fields: list[tuple[int, tuple[int, int, str]]], values: list[int]
    ) -> None:
        fmt = "<B" + "".join(t[2] for _, t in fields)
        self.body += struct.pack(fmt, local, *values)

    def finish(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", Crc.calculate(header))
        content = header + bytes(self.body)
        return content + struct.pack("<H", Crc.calculate(content))


def build_fit(
    samples: list[Sample],
    *,
    start: datetime = datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
    sport: int = SPORT_RUNNING,
    sub_sport: str | None = "street",
    with_session: bool = True,
) -> bytes:
    w = _Writer()
    file_id = [(0, ENUM), (1, UINT16), (4, UINT32)]
    w.define(0, 0, file_id)
    w.data(0, file_id, [4, 1, _fit_ts(start)])

    record = [
        (253, UINT32),
        (2, UINT16),
        (3, UINT8),
        (4, UINT8),
        (53, UINT8),
        (5, UINT32),
        (6, UINT16),
        (41, UINT16),
    ]
    w.define(1, 20, record)
    t0 = _fit_ts(start)
    for i, s in enumerate(samples):
        strides = (s.cadence_spm or 0) / 2
        w.data(
            1,
            record,
            [
                t0 + i,
                int(round((s.altitude_m + 500) * 5)),
                s.heart_rate if s.heart_rate is not None else 0xFF,
                int(strides) if s.cadence_spm else 0xFF,
                int(round((strides - int(strides)) * 128)) if s.cadence_spm else 0xFF,
                int(round(s.distance_m * 100)),
                int(round(s.speed_mps * 1000)),
                int(round(s.gct_ms * 10)) if s.gct_ms else 0xFFFF,
            ],
        )

    if with_session:
        session = [
            (253, UINT32),
            (2, UINT32),
            (5, ENUM),
            (6, ENUM),
            (7, UINT32),
            (8, UINT32),
            (9, UINT32),
        ]
        w.define(2, 18, session)
        n = len(samples)
        w.data(
            2,
            session,
            [
                t0 + n,
                t0,
                sport,
                SUB_SPORT.get(sub_sport or "", 0),
                n * 1000,
                n * 1000,
                int(round(samples[-1].distance_m * 100)),
            ],
        )
    return w.finish()


def synthetic_run(
    minutes: int = 60,
    *,
    speed_mps: float = 3.5,
    cadence_spm: float = 176,
    heart_rate: int = 150,
    gct_ms: float = 240,
    final_fraction: float = 0.2,
    final_cadence_drop: float = 0,
    final_hr_rise: int = 0,
    final_gct_rise: float = 0,
    final_speed_drop: float = 0,
    seed: int = 7,
) -> list[Sample]:
    rng = np.random.default_rng(seed)
    n = minutes * 60
    final_start = int(n * (1 - final_fraction))
    samples: list[Sample] = []
    distance = 0.0
    for i in range(n):
        final = i >= final_start
        speed = speed_mps - (final_speed_drop if final else 0) + rng.normal(0, 0.05)
        distance += speed
        samples.append(
            Sample(
                heart_rate=heart_rate + (final_hr_rise if final else 0) + int(rng.integers(-1, 2)),
                cadence_spm=cadence_spm
                - (final_cadence_drop if final else 0)
                + 2 * int(rng.integers(-1, 2)),
                speed_mps=speed,
                altitude_m=100 + 5 * np.sin(i / 300),
                distance_m=distance,
                gct_ms=gct_ms + (final_gct_rise if final else 0) + float(rng.normal(0, 2)),
            )
        )
    return samples


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample.fit"
    with open(out, "wb") as fh:
        fh.write(build_fit(synthetic_run(70, final_cadence_drop=6)))
    print(f"Wrote {out}: 70' run with mechanical breakdown in the final 20%")
