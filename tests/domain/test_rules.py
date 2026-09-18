"""Tests for `domain.rules`."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dwch.domain.models import (
    DeleteOp,
    Deviation,
    DeviationType,
    MoveOp,
    Plan,
    PlanMeta,
    State,
    Task,
    WriteOp,
)
from dwch.domain.rules import (
    has_blocker,
    has_plan_correction,
    is_development_phase,
    is_phase_abandoned,
    is_phase_closed,
    is_phase_open,
    is_plan_frozen,
    is_planning_phase,
    is_state_consistent,
    is_substantive,
    is_unset_phase,
    next_task_id,
    phase_name_error,
)


def _state(**overrides) -> State:
    """Build a fully-populated state for the predicates under test."""
    base = State(
        harness_version="0.4.0",
        phase_name="phase-01",
        phase_kind="development",
        phase_status="open",
        phase_opened_at="2026-01-01T00:00:00+00:00",
        phase_closed_at="",
        plan_version=1,
        plan_sha256="abc",
        plan_position=0,
        plan_frozen=True,
        verify_ok=False,
        verify_task_id="",
        verify_at="",
        failure_task_id="",
        failure_check_name="",
        failure_excerpt="",
        failure_count=0,
        rollback_count=0,
        last_commit="",
        last_commit_date="",
    )
    return replace(base, **overrides)


def test_is_planning_phase_true() -> None:
    """`is_planning_phase` matches only the planning kind."""
    assert is_planning_phase(_state(phase_kind="planning"))


def test_is_planning_phase_false() -> None:
    """A development phase is not a planning phase."""
    assert not is_planning_phase(_state(phase_kind="development"))


def test_is_development_phase_true() -> None:
    """`is_development_phase` matches only the development kind."""
    assert is_development_phase(_state(phase_kind="development"))


def test_is_unset_phase_true() -> None:
    """`is_unset_phase` matches only the unset kind."""
    assert is_unset_phase(_state(phase_kind="unset"))


def test_is_phase_open_true() -> None:
    """An open status matches."""
    assert is_phase_open(_state(phase_status="open"))


def test_is_phase_closed_true() -> None:
    """A closed status matches."""
    assert is_phase_closed(_state(phase_status="closed"))


def test_is_phase_abandoned_true() -> None:
    """An abandoned status matches."""
    assert is_phase_abandoned(_state(phase_status="abandoned"))


def test_is_plan_frozen_reads_flag() -> None:
    """`is_plan_frozen` mirrors `state.plan_frozen`."""
    assert is_plan_frozen(_state(plan_frozen=True))
    assert not is_plan_frozen(_state(plan_frozen=False))


def test_is_substantive_true_for_code_file() -> None:
    """A step writing a code file is substantive."""
    assert is_substantive([WriteOp(path="src/x.py", content="x = 1\n")])


def test_is_substantive_false_for_deviations_only() -> None:
    """A step that writes only deviation files is not substantive."""
    assert not is_substantive([WriteOp(path=".harness/deviations/t1.toml", content="")])


def test_is_substantive_true_for_delete_outside_prefixes() -> None:
    """A DeleteOp on a code file is substantive."""
    assert is_substantive([DeleteOp(path="src/old.py")])


def test_is_substantive_true_for_move_outside_prefixes() -> None:
    """A MoveOp on a code file is substantive."""
    assert is_substantive([MoveOp(src="src/a.py", dst="src/b.py")])


def test_is_substantive_empty() -> None:
    """An empty op list is not substantive."""
    assert not is_substantive([])


def test_has_blocker_true() -> None:
    """`has_blocker` detects a blocker deviation."""
    dev = Deviation(
        type=DeviationType.BLOCKER,
        affected=(),
        reason="",
        detail="",
    )
    assert has_blocker([dev])


def test_has_blocker_false() -> None:
    """`has_blocker` ignores non-blocker types."""
    dev = Deviation(
        type=DeviationType.ASSUMPTION,
        affected=(),
        reason="",
        detail="",
    )
    assert not has_blocker([dev])


def test_has_plan_correction_true() -> None:
    """`has_plan_correction` detects a plan-correction deviation."""
    dev = Deviation(
        type=DeviationType.PLAN_CORRECTION,
        affected=(),
        reason="",
        detail="",
    )
    assert has_plan_correction([dev])


def test_next_task_id_returns_id() -> None:
    """`next_task_id` returns the task at the given position."""
    plan = Plan(
        meta=PlanMeta(version=1, note=""),
        interfaces=(),
        tasks=(
            Task(
                id="a",
                title="a",
                goal="",
                files=(),
                interfaces=(),
                acceptance=(),
            ),
            Task(
                id="b",
                title="b",
                goal="",
                files=(),
                interfaces=(),
                acceptance=(),
            ),
        ),
    )
    assert next_task_id(plan, 0) == "a"
    assert next_task_id(plan, 1) == "b"


def test_next_task_id_past_end() -> None:
    """`next_task_id` returns None past the end."""
    plan = Plan(meta=PlanMeta(version=1, note=""), interfaces=(), tasks=())
    assert next_task_id(plan, 0) is None


def test_state_consistent_ok() -> None:
    """A populated, valid state is consistent."""
    assert is_state_consistent(_state())


def test_state_consistent_rejects_unknown_kind() -> None:
    """An unknown phase kind is inconsistent."""
    assert not is_state_consistent(_state(phase_kind="bogus"))


def test_state_consistent_rejects_unknown_status() -> None:
    """An unknown phase status is inconsistent."""
    assert not is_state_consistent(_state(phase_status="bogus"))


def test_state_consistent_rejects_empty_phase() -> None:
    """An empty phase name is inconsistent."""
    assert not is_state_consistent(_state(phase_name=""))


def test_state_consistent_rejects_negative_position() -> None:
    """A negative position is inconsistent."""
    assert not is_state_consistent(_state(plan_position=-1))


def test_phase_name_error_ok() -> None:
    """A simple slug passes."""
    assert phase_name_error("00-planning") is None


def test_phase_name_error_underscore() -> None:
    """An underscore is allowed."""
    assert phase_name_error("my_phase") is None


def test_phase_name_error_empty() -> None:
    """An empty name is rejected."""
    assert phase_name_error("") == "phase name must be non-empty"


def test_phase_name_error_space() -> None:
    """A space is rejected."""
    assert "spaces" in phase_name_error("has space")


def test_phase_name_error_newline() -> None:
    """An embedded newline is rejected."""
    err = phase_name_error("a\nb")
    assert err is not None
    assert "newlines" in err or "control" in err


def test_phase_name_error_tab() -> None:
    """An embedded tab is rejected."""
    err = phase_name_error("a\tb")
    assert err is not None
    assert "tabs" in err or "control" in err


def test_phase_name_error_nul() -> None:
    """A NUL byte is rejected."""
    err = phase_name_error("a\x00b")
    assert err is not None
    assert "control" in err


def test_phase_name_error_slash() -> None:
    """A forward slash is rejected."""
    assert "path separators" in phase_name_error("a/b")


def test_phase_name_error_dot() -> None:
    """A single dot is rejected."""
    assert phase_name_error(".") == "phase name must not be '.' or '..'"


@pytest.mark.parametrize("bad", ["a<b", "a>b", 'a"b', "a:b", "a|b", "a?b", "a*b"])
def test_phase_name_error_reserved_chars(bad: str) -> None:
    """Every reserved character is rejected."""
    err = phase_name_error(bad)
    assert err is not None
    assert "invalid characters" in err
