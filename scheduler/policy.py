"""Pure functions defining the Süper Lig pre-match timing policy."""

ANALYSIS_WINDOW_MINUTES = 60
LINEUP_FALLBACK_MINUTES = 30
FINAL_PREDICTION_MINUTES = 15


def analysis_active(minutes_to_kickoff: float) -> bool:
    """Return True only while the fixture is inside the T-60 pre-match window."""
    return (
        0
        < minutes_to_kickoff
        <= ANALYSIS_WINDOW_MINUTES
    )


def should_poll_lineup(minutes_to_kickoff: float) -> bool:
    """Allow lineup checks from T-60 until T-30.

    Workflow runs are already scheduled at five-minute intervals, so this
    function only defines the valid lineup-monitoring time window.
    """
    return (
        LINEUP_FALLBACK_MINUTES
        < minutes_to_kickoff
        <= ANALYSIS_WINDOW_MINUTES
    )


def fallback_due(minutes_to_kickoff: float) -> bool:
    """Return True once missing lineup information must stop being a blocker."""
    return (
        0
        < minutes_to_kickoff
        <= LINEUP_FALLBACK_MINUTES
    )


def final_prediction_due(minutes_to_kickoff: float) -> bool:
    """Return True only inside the final T-15 prediction window."""
    return (
        0
        < minutes_to_kickoff
        <= FINAL_PREDICTION_MINUTES
    )


def outside_pre_match_window(minutes_to_kickoff: float) -> bool:
    """Return True when no pre-match analysis or prediction work is required."""
    return (
        minutes_to_kickoff <= 0
        or minutes_to_kickoff
        > ANALYSIS_WINDOW_MINUTES
    )
