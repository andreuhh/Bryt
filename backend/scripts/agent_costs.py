"""Claude API spend per user and month, split by agent (from AgentExecutionLog.cost_usd).

.venv/bin/python -m scripts.agent_costs [--user <uuid>] [--months 3]
"""

import argparse
import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlmodel import col, select

from app.core.database import SessionFactory, engine
from app.models import AgentExecutionLog


async def main(user_id: uuid.UUID | None, months: int) -> None:
    since = datetime.now(UTC) - timedelta(days=31 * months)
    async with SessionFactory() as session:
        stmt = select(AgentExecutionLog).where(col(AgentExecutionLog.created_at) >= since)
        if user_id is not None:
            stmt = stmt.where(AgentExecutionLog.user_id == user_id)
        logs = list((await session.exec(stmt)).all())
    await engine.dispose()

    # (user, month) → agent → [calls, cost]
    table: dict[tuple[uuid.UUID, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0.0])
    )
    unpriced = 0
    for log in logs:
        row = table[(log.user_id, log.created_at.strftime("%Y-%m"))][log.agent_name.value]
        row[0] += 1
        row[1] += log.cost_usd or 0.0
        unpriced += log.cost_usd is None and bool(log.input_tokens)
    for (user, month), agents in sorted(table.items(), key=lambda kv: (kv[0][1], str(kv[0][0]))):
        total = sum(cost for _, cost in agents.values())
        print(f"\n{month}  user {user}  total ${total:.2f}")
        for agent, (calls, cost) in sorted(agents.items(), key=lambda kv: -kv[1][1]):
            print(f"  {agent:<24} {int(calls):>4} calls  ${cost:.3f}")
    if unpriced:
        print(f"\n{unpriced} runs on models missing from app/agents/pricing.py (not counted)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=uuid.UUID, default=None)
    parser.add_argument("--months", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main(args.user, args.months))
