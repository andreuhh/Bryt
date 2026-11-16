"""Move every row (and stored .fit file) of one user to another user id.

Used once when switching from the development user (X-Dev-User-Id) to a real Supabase
account: sign in once (that creates the `users` row), then
    .venv/bin/python -m scripts.reassign_user --from <dev uuid> --to-email <email>  # dry run
    .venv/bin/python -m scripts.reassign_user --from <dev uuid> --to-email <email> --apply
The target is chosen by the email it signed up with, so data can only land on that account.
It must not own any data yet. The source `users` row is deleted at the end.
"""

import argparse
import asyncio
import shutil
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers every table in the metadata)
from app.core.config import get_settings
from app.core.database import engine

# Profile fields that live on `users` itself (the rest of the profile is a tenant table)
USER_FIELDS = ("display_name", "timezone", "onboarding_completed")


def tenant_tables() -> list[str]:
    return sorted(
        t.name for t in SQLModel.metadata.sorted_tables if "user_id" in t.c and t.name != "users"
    )


async def main(source: uuid.UUID, target_email: str, apply: bool) -> None:
    tables = tenant_tables()
    async with engine.begin() as conn:
        target = (
            await conn.execute(
                text("SELECT id FROM users WHERE lower(email) = lower(:e)"), {"e": target_email}
            )
        ).scalar_one_or_none()
        if target is None:
            raise SystemExit(f"no user with email {target_email}: sign in once with Supabase first")
        print(f"target: {target_email} ({target})\n")
        users = {
            row.id: row
            for row in (
                await conn.execute(
                    text("SELECT * FROM users WHERE id IN (:a, :b)"), {"a": source, "b": target}
                )
            ).all()
        }
        if source not in users:
            raise SystemExit(f"source user {source} not found")

        counts: dict[str, int] = {}
        for table in tables:
            for user_id in (source, target):
                n = (
                    await conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE user_id = :u"), {"u": user_id}
                    )
                ).scalar_one()
                if user_id == target and n:
                    raise SystemExit(f"target already owns {n} rows in {table}: aborting")
                if user_id == source:
                    counts[table] = n

        for table, n in counts.items():
            print(f"{table:28} {n:6} rows")
        if not apply:
            print("\nDry run: nothing changed. Re-run with --apply.")
            return

        for table in tables:
            await conn.execute(
                text(f"UPDATE {table} SET user_id = :t WHERE user_id = :s"),
                {"s": source, "t": target},
            )
        # Stored .fit files are keyed by user: fit/{user_id}/{sha256}.fit
        await conn.execute(
            text(
                "UPDATE activities SET fit_storage_path = "
                "replace(fit_storage_path, :old, :new) WHERE user_id = :t"
            ),
            {"old": f"fit/{source}/", "new": f"fit/{target}/", "t": target},
        )
        src = users[source]
        await conn.execute(
            text(
                "UPDATE users SET "
                + ", ".join(f"{f} = :{f}" for f in USER_FIELDS)
                + " WHERE id = :t"
            ),
            {f: getattr(src, f) for f in USER_FIELDS} | {"t": target},
        )
        await conn.execute(text("DELETE FROM users WHERE id = :s"), {"s": source})

    base = Path(get_settings().storage_dir) / "fit"
    if (base / str(source)).exists():
        (base / str(target)).mkdir(parents=True, exist_ok=True)
        for file in (base / str(source)).iterdir():
            shutil.move(file, base / str(target) / file.name)
        (base / str(source)).rmdir()
    print(f"\nMoved to {target}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="source", type=uuid.UUID, required=True)
    parser.add_argument("--to-email", dest="target_email", required=True)
    parser.add_argument("--apply", action="store_true", help="perform the move (default: dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.source, args.target_email, args.apply))
