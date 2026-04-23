from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_WORKDIR = Path(".work/hocrgen")
STAGE_DIR_ALIASES = {
    "review-export": "review",
    "review_export": "review",
}


def normalize_stage_dir_name(stage_name: str) -> str:
    normalized = stage_name.replace("-", "_")
    return STAGE_DIR_ALIASES.get(stage_name, STAGE_DIR_ALIASES.get(normalized, normalized))


@dataclass(frozen=True)
class RunContext:
    run_id: str
    profile_id: str
    dry_run: bool
    work_root: Path
    run_dir: Path
    log_dir: Path
    created_at: str

    def stage_dir(self, stage_name: str) -> Path:
        return self.run_dir / normalize_stage_dir_name(stage_name)


def make_run_id(now: datetime | None = None) -> str:
    timestamp = now or datetime.now(UTC)
    return timestamp.strftime("%Y%m%dT%H%M%S%fZ")


def create_run_context(profile_id: str, dry_run: bool, workdir: Path | None = None) -> RunContext:
    work_root = (workdir or DEFAULT_WORKDIR).resolve()
    run_id = make_run_id()
    run_dir = work_root / "runs" / run_id
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        profile_id=profile_id,
        dry_run=dry_run,
        work_root=work_root,
        run_dir=run_dir,
        log_dir=log_dir,
        created_at=datetime.now(UTC).isoformat(),
    )
