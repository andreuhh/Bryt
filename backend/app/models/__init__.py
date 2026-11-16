"""SQLModel table models: PostgreSQL shared state, multi-tenant via user_id.

Importing this package registers every table on SQLModel.metadata (used by Alembic).
"""

from app.models.activity import Activity, ActivityStream
from app.models.agent_log import AgentExecutionLog
from app.models.training import TrainingPlan, Workout, WorkoutRevision
from app.models.user import PersonalBest, User, UserLifestyleProfile
from app.models.wellness import DailyWellness

__all__ = [
    "Activity",
    "ActivityStream",
    "AgentExecutionLog",
    "DailyWellness",
    "PersonalBest",
    "TrainingPlan",
    "User",
    "UserLifestyleProfile",
    "Workout",
    "WorkoutRevision",
]
