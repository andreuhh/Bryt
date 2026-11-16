"""Recompute Activity.computed_metrics from the stored original .fit files.

Run after changing the deterministic analysis (e.g. new divergence signals):
    .venv/bin/python -m scripts.recompute_metrics [--user <uuid>]
"""

import argparse
import asyncio
import uuid
from pathlib import Path

from sqlmodel import col, select

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.models import Activity
from app.services.fit_parser import FitParseError, parse_fit


async def main(user_id: uuid.UUID | None) -> None:
    base = Path(get_settings().storage_dir)
    async with SessionFactory() as session:
        stmt = select(Activity).where(col(Activity.fit_storage_path).is_not(None))
        if user_id is not None:
            stmt = stmt.where(Activity.user_id == user_id)
        activities = list((await session.exec(stmt)).all())
        updated = 0
        for activity in activities:
            path = base / (activity.fit_storage_path or "")
            if not path.exists():
                print(f"skip {activity.id}: file missing ({path})")
                continue
            try:
                parsed = await asyncio.to_thread(parse_fit, path.read_bytes())
            except FitParseError as exc:
                print(f"skip {activity.id}: {exc}")
                continue
            activity.computed_metrics = parsed.computed.model_dump(mode="json")
            session.add(activity)
            updated += 1
        await session.commit()
    await engine.dispose()
    print(f"recomputed {updated}/{len(activities)} activities")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=uuid.UUID, default=None)
    asyncio.run(main(parser.parse_args().user))
