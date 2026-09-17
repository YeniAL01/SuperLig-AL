"""Prediction engine unit tests."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Fixture
from prediction.confidence import ConfidenceEngine
from prediction.engine import PredictionEngine, TeamForm


def fixture_in(minutes: int = 60) -> Fixture:
    """Create a future fixture for deterministic prediction tests."""
    return Fixture(
        1,
        "Ev",
        "Dep",
        datetime.now(UTC) + timedelta(minutes=minutes),
    )


def form(
    *,
    scored: float = 1.5,
    conceded: float = 1.0,
    form_points: float = 1.5,
    samples: int = 10,
    elo: float = 1500.0,
) -> TeamForm:
    """Create a valid team-form snapshot."""
    return TeamForm(
        scored,
        conceded,
        form_points,
        samples,
        elo=elo,
    )


def test_prediction_is_bounded() -> None:
    """The engine emits a valid pre-match prediction."""
    fixture = fixture_in()
    team_form = form()

    prediction = PredictionEngine().predict(
        fixture,
        team_form,
        team_form,
        70,
        True,
    )

    assert 0 <= prediction.home_goals <= 15
    assert 0 <= prediction.away_goals <= 15

    assert prediction.winner in {
        "Ev",
        "Dep",
        "Beraberlik",
    }

    assert 0 <= prediction.confidence <= 100


def test_prediction_contains_all_required_markets() -> None:
    """Every forecast must persist 1X2, O/U 2.5 and BTTS."""
    fixture = fixture_in()
    team_form = form()

    prediction = PredictionEngine().predict(
        fixture,
        team_form,
        team_form,
        lineup_verified=False,
    )

    assert set(prediction.markets) == {
        "1x2",
        "ou25",
        "btts",
    }

    assert set(
        prediction.markets["1x2"]["probabilities"]
    ) == {
        "HOME",
        "DRAW",
        "AWAY",
    }

    assert set(
        prediction.markets["ou25"]["probabilities"]
    ) == {
        "OVER",
        "UNDER",
    }

    assert set(
        prediction.markets["btts"]["probabilities"]
    ) == {
        "YES",
        "NO",
    }


def test_market_probabilities_are_normalized() -> None:
    """Every market probability distribution must sum to one."""
    fixture = fixture_in()

    prediction = PredictionEngine().predict(
        fixture,
        form(
            scored=2.0,
            conceded=0.8,
            form_points=2.2,
            elo=1600.0,
        ),
        form(
            scored=1.1,
            conceded=1.6,
            form_points=1.0,
            elo=1450.0,
        ),
        lineup_verified=True,
    )

    for market in (
        "1x2",
        "ou25",
        "btts",
    ):
        probabilities = prediction.markets[
            market
        ]["probabilities"]

        assert all(
            0 <= value <= 1
            for value in probabilities.values()
        )

        assert sum(
            probabilities.values()
        ) == pytest.approx(
            1.0,
            abs=1e-9,
        )


def test_factor_snapshot_is_saved_for_every_market() -> None:
    """Learning must receive immutable factor evidence per market."""
    fixture = fixture_in()

    prediction = PredictionEngine().predict(
        fixture,
        form(),
        form(),
        lineup_verified=True,
    )

    assert set(
        prediction.factor_snapshot
    ) == {
        "1x2",
        "ou25",
        "btts",
    }

    expected_factors = {
        "form",
        "home_away",
        "elo",
        "goals",
        "lineup",
        "availability",
        "odds_support",
        "model_signal",
    }

    for market in (
        "1x2",
        "ou25",
        "btts",
    ):
        assert set(
            prediction.factor_snapshot[
                market
            ]
        ) == expected_factors


def test_sample_count_is_not_used_as_player_availability() -> None:
    """Historical sample sufficiency must not impersonate injury data."""
    fixture = fixture_in()

    prediction = PredictionEngine().predict(
        fixture,
        form(
            samples=50,
        ),
        form(
            samples=50,
        ),
        lineup_verified=False,
    )

    for market in (
        "1x2",
        "ou25",
        "btts",
    ):
        assert (
            prediction.factor_snapshot[
                market
            ]["availability"]
            == 0.0
        )


def test_verified_lineup_is_recorded_in_factor_snapshot() -> None:
    """Verified starting XI must be represented as real evidence."""
    fixture = fixture_in()

    prediction = PredictionEngine().predict(
        fixture,
        form(),
        form(),
        lineup_verified=True,
    )

    for market in (
        "1x2",
        "ou25",
        "btts",
    ):
        assert (
            prediction.factor_snapshot[
                market
            ]["lineup"]
            == 1.0
        )


def test_missing_lineup_does_not_block_prediction() -> None:
    """A missing XI must not prevent the final forecast."""
    fixture = fixture_in(
        10
    )

    prediction = PredictionEngine().predict(
        fixture,
        form(),
        form(),
        lineup_verified=False,
    )

    assert prediction.lineup_verified is False

    assert prediction.outcome in {
        "HOME",
        "DRAW",
        "AWAY",
    }


def test_top_level_1x2_matches_market_snapshot() -> None:
    """Legacy top-level fields must remain synchronized with 1X2."""
    fixture = fixture_in()

    prediction = PredictionEngine().predict(
        fixture,
        form(
            scored=2.1,
            conceded=0.7,
            form_points=2.4,
            elo=1650.0,
        ),
        form(
            scored=0.9,
            conceded=1.8,
            form_points=0.8,
            elo=1420.0,
        ),
        lineup_verified=True,
    )

    market = prediction.markets[
        "1x2"
    ]

    assert prediction.probabilities == (
        market["probabilities"]
    )

    assert prediction.confidence == pytest.approx(
        market["confidence"]
    )


def test_score_is_compatible_with_predicted_outcome() -> None:
    """Predicted score must agree with the selected 1X2 outcome."""
    fixture = fixture_in()

    prediction = PredictionEngine().predict(
        fixture,
        form(
            scored=2.3,
            conceded=0.8,
            form_points=2.5,
            elo=1650.0,
        ),
        form(
            scored=0.8,
            conceded=1.9,
            form_points=0.7,
            elo=1400.0,
        ),
        lineup_verified=True,
    )

    if prediction.outcome == "HOME":
        assert (
            prediction.home_goals
            > prediction.away_goals
        )

    elif prediction.outcome == "AWAY":
        assert (
            prediction.away_goals
            > prediction.home_goals
        )

    else:
        assert (
            prediction.home_goals
            == prediction.away_goals
        )


def test_prediction_cannot_be_created_after_kickoff() -> None:
    """The engine must never generate a post-kickoff forecast."""
    kickoff = datetime.now(
        UTC
    ) - timedelta(
        seconds=1
    )

    fixture = Fixture(
        1,
        "Ev",
        "Dep",
        kickoff,
    )

    with pytest.raises(
        ValueError,
        match="before kickoff",
    ):
        PredictionEngine().predict(
            fixture,
            form(),
            form(),
            lineup_verified=False,
            as_of=datetime.now(UTC),
        )


def test_prediction_timestamp_must_be_timezone_aware() -> None:
    """Pre-match snapshots must use timezone-aware timestamps."""
    fixture = fixture_in()

    naive = datetime.now().replace(
        tzinfo=None
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        PredictionEngine().predict(
            fixture,
            form(),
            form(),
            lineup_verified=False,
            as_of=naive,
        )


def test_unverified_lineup_is_penalized_by_legacy_confidence_engine() -> None:
    """Preserve the existing confidence-engine lineup behavior."""
    team_form = form(
        scored=1.2,
        conceded=1.2,
        form_points=1.0,
    )

    engine = ConfidenceEngine()

    assert engine.calculate(
        team_form,
        team_form,
        True,
        0.5,
    ) > engine.calculate(
        team_form,
        team_form,
        False,
        0.5,
    )
