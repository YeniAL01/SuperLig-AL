"""Pure functions defining the pre-match time policy."""
def should_poll_lineup(minutes_to_kickoff: float) -> bool:
    """Allow five-minute lineup checks from T-60 through T-20."""
    return 20 <= minutes_to_kickoff <= 60 and abs(minutes_to_kickoff % 5) < 0.2

def fallback_due(minutes_to_kickoff: float) -> bool:
    """Identify the T-18 fallback-analysis point."""
    return 17.5 <= minutes_to_kickoff <= 18.5
