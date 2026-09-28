from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from manutencao_pro.constants import (
    APT_STEP_IDS,
    MAX_HISTORY,
    RESULT_STEPS,
    STEP_IDS,
    step_title,
)
from manutencao_pro.parser import (
    RebootMarker,
    ResultMarker,
    StepMarker,
    WarnMarker,
    parse_line,
)

PENDING = "pending"
RUNNING = "running"
SUCCESS = "success"
WARNING = "warning"
ERROR = "error"
CANCELLED = "cancelled"

_SUCCESS_STATES = frozenset({"ok", "rebuilt", "fixed", "upgraded", "ahead"})
_INFO_STATES = frozenset({"missing", "no_display", "fail", "no_pkg", "skip"})
_ERROR_STATES = frozenset({"loaded", "wrong", "broken"})


def classify(key: str, state: str) -> str:
    if key == "packages" and state == "fail":
        return "error"
    if state in _SUCCESS_STATES:
        return "success"
    if state in _ERROR_STATES:
        return "error"
    if state in _INFO_STATES:
        return "info"
    return "warning"


@dataclass
class StepState:
    step_id: str
    title: str
    status: str = PENDING
    saw_warn: bool = False


@dataclass
class RunRecord:
    started_at: str
    finished_at: str
    duration_seconds: float
    status: str
    warnings: list[str]
    reboot_reasons: list[str]
    results: dict[str, str]
    log: str
    exit_code: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "warnings": self.warnings,
            "reboot_reasons": self.reboot_reasons,
            "results": self.results,
            "log": self.log,
            "exit_code": self.exit_code,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RunRecord:
        warnings = raw.get("warnings", [])
        reasons = raw.get("reboot_reasons", [])
        results = raw.get("results", {})
        return cls(
            started_at=str(raw.get("started_at", "")),
            finished_at=str(raw.get("finished_at", "")),
            duration_seconds=float(raw.get("duration_seconds", 0)),
            status=str(raw.get("status", "error")),
            warnings=[str(item) for item in warnings] if isinstance(warnings, list) else [],
            reboot_reasons=[str(item) for item in reasons] if isinstance(reasons, list) else [],
            results={str(key): str(value) for key, value in results.items()} if isinstance(results, dict) else {},
            log=str(raw.get("log", "")),
            exit_code=int(raw.get("exit_code", 0)),
        )


def state_dir() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    base = Path(configured) if configured else Path.home() / ".local" / "state"
    return base / "manutencao-pro"


class HistoryStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else state_dir()

    @property
    def path(self) -> Path:
        return self.directory / "history.json"

    def load(self) -> list[RunRecord]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return []
        runs = payload.get("runs") if isinstance(payload, dict) else None
        if not isinstance(runs, list):
            return []
        records: list[RunRecord] = []
        for item in runs:
            if isinstance(item, dict):
                records.append(RunRecord.from_dict(item))
        return records[:MAX_HISTORY]

    def latest(self) -> RunRecord | None:
        runs = self.load()
        if not runs:
            return None
        return runs[0]

    def append(self, record: RunRecord) -> None:
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.directory, 0o700)
        kept = [record, *self.load()][:MAX_HISTORY]
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps({"runs": [item.to_dict() for item in kept]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)


@dataclass
class RunModel:
    steps: list[StepState] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reboot_reasons: list[str] = field(default_factory=list)
    results: dict[str, str] = field(default_factory=dict)
    status: str = PENDING
    exit_code: int = 0
    current_step_id: str = "apt-update"
    _active: bool = False
    _started_at: datetime | None = None
    _finished_at: datetime | None = None
    _started_mono: float = 0.0
    _finished_mono: float = 0.0

    def begin(self) -> None:
        self.steps = [StepState(step_id, step_title(step_id)) for step_id in STEP_IDS]
        self.warnings = []
        self.reboot_reasons = []
        self.results = {}
        self.status = RUNNING
        self.exit_code = 0
        self.current_step_id = "apt-update"
        self._active = True
        self._started_at = datetime.now().astimezone()
        self._finished_at = None
        self._started_mono = _monotonic()
        self._finished_mono = 0.0

    @property
    def can_cancel(self) -> bool:
        return self._active and self.current_step_id not in APT_STEP_IDS

    @property
    def fraction(self) -> float:
        if not self.steps:
            return 0.0
        if self.status not in {RUNNING, PENDING}:
            return 1.0
        done = sum(1 for step in self.steps if step.status in {SUCCESS, WARNING, ERROR, CANCELLED})
        return done / len(self.steps)

    @property
    def progress_index(self) -> tuple[int, int]:
        total = len(self.steps) or 1
        if self.status not in {RUNNING, PENDING}:
            return (total, total)
        for position, step in enumerate(self.steps, start=1):
            if step.step_id == self.current_step_id:
                return (position, total)
        return (1, total)

    def consume(self, line: str) -> None:
        marker = parse_line(line)
        if isinstance(marker, StepMarker):
            self._start_step(marker)
            return
        if isinstance(marker, WarnMarker):
            self.warnings.append(marker.message)
            current = self._current()
            if current is not None:
                current.saw_warn = True
            return
        if isinstance(marker, RebootMarker):
            self.reboot_reasons.append(marker.reason)
            return
        if isinstance(marker, ResultMarker):
            self.results[marker.key] = marker.state

    def finish(self, exit_code: int, term_sig: int | None) -> None:
        self.exit_code = exit_code
        self._finished_at = datetime.now().astimezone()
        self._finished_mono = _monotonic()
        self._active = False
        cancelled = term_sig == 15 or exit_code == 143
        current = self._current()
        if cancelled:
            if current is not None and current.status == RUNNING:
                current.status = CANCELLED
            self.status = CANCELLED
            return
        if current is not None:
            self._complete(current)
        self._apply_results()
        self.status = self._overall(exit_code)

    def to_record(self, log: str) -> RunRecord:
        started = self._started_at or datetime.now().astimezone()
        finished = self._finished_at or started
        duration = 0.0
        if self._finished_mono and self._started_mono:
            duration = round(self._finished_mono - self._started_mono, 1)
        return RunRecord(
            started_at=started.isoformat(timespec="seconds"),
            finished_at=finished.isoformat(timespec="seconds"),
            duration_seconds=duration,
            status=self.status,
            warnings=list(self.warnings),
            reboot_reasons=list(self.reboot_reasons),
            results=dict(self.results),
            log=log,
            exit_code=self.exit_code,
        )

    def _start_step(self, marker: StepMarker) -> None:
        current = self._current()
        if current is not None and current.status == RUNNING:
            self._complete(current)
        step = self._by_id(marker.step_id)
        if step is None:
            step = StepState(marker.step_id, marker.title, RUNNING)
            self.steps.append(step)
        else:
            step.title = marker.title
            step.status = RUNNING
        self.current_step_id = marker.step_id

    def _complete(self, step: StepState) -> None:
        if step.status != RUNNING:
            return
        step.status = WARNING if step.saw_warn else SUCCESS

    def _apply_results(self) -> None:
        for key, value in self.results.items():
            if key == "packages" and value == "fail":
                self._mark_apt_failure()
                continue
            step_id = RESULT_STEPS.get(key)
            if step_id is None:
                continue
            self._apply_kind(step_id, classify(key, value))

    def _mark_apt_failure(self) -> None:
        for step_id in APT_STEP_IDS:
            step = self._by_id(step_id)
            if step is not None and step.saw_warn and step.status != PENDING:
                step.status = ERROR

    def _apply_kind(self, step_id: str, kind: str) -> None:
        step = self._by_id(step_id)
        if step is None or step.status in {PENDING, CANCELLED}:
            return
        if kind == "error":
            step.status = ERROR
        elif kind == "warning" and step.status == SUCCESS:
            step.status = WARNING

    def _overall(self, exit_code: int) -> str:
        if any(classify(key, value) == "error" for key, value in self.results.items()):
            return "error"
        if exit_code not in (0,) and not self.results:
            return "error"
        if self.reboot_reasons:
            return "reboot"
        if self.warnings or any(classify(key, value) == "warning" for key, value in self.results.items()):
            return "warning"
        return "ok"

    def _current(self) -> StepState | None:
        return self._by_id(self.current_step_id)

    def _by_id(self, step_id: str) -> StepState | None:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None


def _monotonic() -> float:
    import time

    return time.monotonic()
