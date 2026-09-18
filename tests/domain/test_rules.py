"""Tests for `domain.rules`."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dwch.domain.models import (
    Deviation,
    DeviationType,
    FileSpec,
    State,
)
from dwch.domain.rules import (
    has_blocker,
    is_development_phase,
    is_phase_closed,
    is_planning_phase,
    is_roadmap_frozen,
    is_state_consistent,
    is_substantive,
    is_unset_phase,
    phase_name_error,
)


def _state(**overrides) -> State:
    """Build a fully-populated state for the predicates under test."""
    base = State(
        harness_version="0.3.0",
        current_phase="phase-01",
        phase_kind="development",
        current_step=1,
        last_commit="",
        last_commit_date="",
        roadmap_version=1,
        roadmap_step=0,
        roadmap_frozen=True,
        rollback_count=0,
        last_opened="",
        last_closed="",
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


def test_is_roadmap_frozen_reads_flag() -> None:
    """`is_roadmap_frozen` mirrors `state.roadmap_frozen`."""
    assert is_roadmap_frozen(_state(roadmap_frozen=True))
    assert not is_roadmap_frozen(_state(roadmap_frozen=False))


def test_is_phase_closed_false_when_never_closed() -> None:
    """An empty `last_closed` means the phase is open."""
    assert not is_phase_closed(
        _state(last_opened="2026-01-01T00:00:00+00:00", last_closed="")
    )


def test_is_phase_closed_true_after_close() -> None:
    """A close timestamp at or after open means the phase is closed."""
    assert is_phase_closed(
        _state(
            last_opened="2026-01-01T00:00:00+00:00",
            last_closed="2026-01-01T00:01:00+00:00",
        )
    )


def test_is_phase_closed_false_before_close() -> None:
    """A close timestamp earlier than open means the phase is open."""
    assert not is_phase_closed(
        _state(
            last_opened="2026-01-01T00:01:00+00:00",
            last_closed="2026-01-01T00:00:00+00:00",
        )
    )


def test_is_substantive_true_for_code_file() -> None:
    """A step writing a code file is substantive."""
    specs = [FileSpec(path="src/x.py", content="x = 1\n")]
    assert is_substantive(specs)


def test_is_substantive_false_for_deviations_only() -> None:
    """A step that writes only deviation files is not substantive."""
    specs = [FileSpec(path=".harness/deviations/step-01.toml", content="")]
    assert not is_substantive(specs)


def test_is_substantive_exempts_handoff() -> None:
    """Writing only `.harness/handoff.md` is not substantive."""
    specs = [FileSpec(path=".harness/handoff.md", content="")]
    assert not is_substantive(specs)


def test_is_substantive_exempts_summaries() -> None:
    """Writing only a phase summary is not substantive."""
    specs = [FileSpec(path=".harness/summaries/p1.md", content="")]
    assert not is_substantive(specs)


def test_has_blocker_true() -> None:
    """`has_blocker` detects a blocker deviation."""
    dev = Deviation(
        type=DeviationType.BLOCKER,
        affected=(),
        reason="",
        detail="",
        auto=False,
    )
    assert has_blocker([dev])


def test_has_blocker_false() -> None:
    """`has_blocker` ignores non-blocker types."""
    dev = Deviation(
        type=DeviationType.ASSUMPTION,
        affected=(),
        reason="",
        detail="",
        auto=False,
    )
    assert not has_blocker([dev])


def test_state_consistent_ok() -> None:
    """A populated, valid state is consistent."""
    assert is_state_consistent(_state())


def test_state_consistent_rejects_unknown_kind() -> None:
    """An unknown phase kind is inconsistent."""
    assert not is_state_consistent(_state(phase_kind="bogus"))


def test_state_consistent_rejects_empty_phase() -> None:
    """An empty phase name is inconsistent."""
    assert not is_state_consistent(_state(current_phase=""))


def test_state_consistent_rejects_negative_step() -> None:
    """A negative counter is inconsistent."""
    assert not is_state_consistent(_state(current_step=-1))


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


def test_phase_name_error_leading_space() -> None:
    """Leading whitespace is rejected."""
    assert "whitespace" in phase_name_error(" leading")


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


def test_phase_name_error_backslash() -> None:
    """A backslash is rejected."""
    assert "path separators" in phase_name_error("a\\b")


def test_phase_name_error_dot() -> None:
    """A single dot is rejected."""
    assert phase_name_error(".") == "phase name must not be '.' or '..'"


def test_phase_name_error_dotdot() -> None:
    """Two dots are rejected."""
    assert phase_name_error("..") == "phase name must not be '.' or '..'"


@pytest.mark.parametrize("bad", ["a<b", "a>b", 'a"b', "a:b", "a|b", "a?b", "a*b"])
def test_phase_name_error_reserved_chars(bad: str) -> None:
    """Every reserved character is rejected."""
    err = phase_name_error(bad)
    assert err is not None
    assert "invalid characters" in err
