import { IconCheck, IconStar } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import type { Workout } from "@/lib/types";

export function WorkoutBadges({ workout, compact = false }: { workout: Workout; compact?: boolean }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {workout.is_key_session && (
        <Badge tone="pace" title="Sessione chiave">
          <IconStar width={12} height={12} />
          {!compact && "Chiave"}
        </Badge>
      )}
      {workout.session_slot !== "SINGLE" && <Badge>{workout.session_slot}</Badge>}
      {workout.status === "MODIFIED" && (
        <Badge title={workout.modification_reason ?? undefined}>
          Modificata
        </Badge>
      )}
      {workout.status === "COMPLETED" && (
        <Badge tone="pace">
          <IconCheck width={12} height={12} />
          {!compact && "Fatto"}
        </Badge>
      )}
      {workout.detail_level === "PROVISIONAL" && workout.workout_type !== "REST" && (
        <Badge tone="outline" title="Passi e dettagli confermati due settimane prima">
          Provvisoria
        </Badge>
      )}
    </span>
  );
}
