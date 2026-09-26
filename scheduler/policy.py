"""Pure functions defining the Süper Lig pre-match timing policy."""

ANALYSIS_WINDOW_MINUTES = 60
LINEUP_RETRY_MINUTES = 10
MAX_LINEUP_ATTEMPTS = 3


def analysis_active(minutes_to_kickoff: float) -> bool:
    """Return True only while the fixture is inside the T-60 pre-match window."""
    return 0 < minutes_to_kickoff <= ANALYSIS_WINDOW_MINUTES


def lineup_retry_due(seconds_since_last_check: float | None) -> bool:
    """Allow the next XI lookup only after the ten-minute retry interval."""
    return (
        seconds_since_last_check is None
        or seconds_since_last_check >= LINEUP_RETRY_MINUTES * 60
    )


def fallback_due(attempts: int, lineup_verified: bool) -> bool:
    """Release the XI blocker after three unsuccessful official-XI checks."""
    return not lineup_verified and attempts >= MAX_LINEUP_ATTEMPTS


def prediction_due(
    minutes_to_kickoff: float,
    lineup_verified: bool,
    attempts: int,
) -> bool:
    """Build as soon as XI is verified, or after the third failed check."""
    return analysis_active(minutes_to_kickoff) and (
        lineup_verified
        or fallback_due(attempts, lineup_verified)
    )


def outside_pre_match_window(minutes_to_kickoff: float) -> bool:
    """Return True when no pre-match analysis or prediction work is required."""
    return not analysis_active(minutes_to_kickoff)
