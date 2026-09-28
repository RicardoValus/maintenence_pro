from __future__ import annotations

import re
from dataclasses import dataclass

_STEP = re.compile(r"^@@STEP (\d+)/(\d+) ([a-z0-9-]+) (.*)$")
_RESULT = re.compile(r"^@@RESULT ([a-z0-9_]+)=([A-Za-z0-9_]+)$")
_REBOOT = re.compile(r"^@@REBOOT (.+)$")
_WARN = re.compile(r"^@@WARN (.+)$")


@dataclass(frozen=True)
class StepMarker:
    index: int
    total: int
    step_id: str
    title: str


@dataclass(frozen=True)
class ResultMarker:
    key: str
    state: str


@dataclass(frozen=True)
class RebootMarker:
    reason: str


@dataclass(frozen=True)
class WarnMarker:
    message: str


@dataclass(frozen=True)
class TextLine:
    text: str


Marker = StepMarker | ResultMarker | RebootMarker | WarnMarker | TextLine


def parse_line(line: str) -> Marker:
    step = _STEP.match(line)
    if step is not None:
        return StepMarker(int(step.group(1)), int(step.group(2)), step.group(3), step.group(4))
    result = _RESULT.match(line)
    if result is not None:
        return ResultMarker(result.group(1), result.group(2))
    reboot = _REBOOT.match(line)
    if reboot is not None:
        return RebootMarker(reboot.group(1))
    warning = _WARN.match(line)
    if warning is not None:
        return WarnMarker(warning.group(1))
    return TextLine(line)
