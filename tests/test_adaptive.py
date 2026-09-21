from datetime import UTC, datetime, timedelta

import pytest

from learning.adaptive import (
    DEFAULT_FACTORS,
    build_learning_samples,
    calibrated_confidence,
    factor_snapshot,
    market_learning,
    update_learning_state,
)
from learning.performance import (
    score_prediction,
    summarize,
)


def _result(
    *,
    fixture_id="1",
    home="A",
    away="B",
    home_goals=2,
    away_goals=1,
):
    return {
        "fixture_id": fixture_id,
        "fixture": f"{home} - {away}",
        "home_team": home,
        "away_team": away,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "kickoff": datetime.now(
            UTC
        ).isoformat(),
    }


def _prediction(
    *,
    fixture_id="1",
    home="A",
    away="B",
    outcome="HOME",
    ou25="OVER",
    btts="YES",
    confidence=70.0,
    delivered=True,
):
    factors = factor_snapshot(
        form=0.4,
        home_away=0.18,
        elo=0.3,
        goals=0.2,
        lineup=1.0,
        availability=0.0,
        odds_support=0.0,
        model_signal=0.25,
    )

    return {
        "fixture_id": fixture_id,
        "fixture": f"{home} - {away}",
        "home_team": home,
        "away_team": away,
        "outcome": outcome,
        "confidence": confidence,
        "delivered": delivered,
        "markets": {
            "1x2": {
                "selection": outcome,
                "confidence": confidence,
                "factors": dict(
                    factors
                ),
            },
            "ou25": {
                "selection": ou25,
                "confidence": confidence,
                "factors": dict(
                    factors
                ),
            },
            "btts": {
                "selection": btts,
                "confidence": confidence,
                "factors": dict(
                    factors
                ),
            },
        },
        "factor_snapshot": {
            "1x2": dict(
                factors
            ),
            "ou25": dict(
                factors
            ),
            "btts": dict(
                factors
            ),
        },
    }


def test_metrics_and_empty_state():
    metrics = summarize(
        []
    )

    assert metrics["all"]["accuracy"] is None
    assert (
        metrics["all"]["winner_accuracy"]
        is None
    )
    assert metrics["all"]["count"] == 0


def test_legacy_winner_scoring_all_outcomes():
    result_home = _result(
        home_goals=2,
        away_goals=1,
    )

    result_draw = _result(
        home_goals=1,
        away_goals=1,
    )

    result_away = _result(
        home_goals=0,
        away_goals=2,
    )

    home_prediction = {
        "fixture": "A - B",
        "winner": "A",
    }

    draw_prediction = {
        "fixture": "A - B",
        "winner": "Beraberlik",
    }

    away_prediction = {
        "fixture": "A - B",
        "winner": "B",
    }

    assert score_prediction(
        home_prediction,
        result_home,
    )["winner_correct"] is True

    assert score_prediction(
        draw_prediction,
        result_draw,
    )["winner_correct"] is True

    assert score_prediction(
        away_prediction,
        result_away,
    )["winner_correct"] is True


def test_factor_snapshot_contains_expected_factors():
    snapshot = factor_snapshot(
        form=0.1,
        home_away=0.2,
        elo=0.3,
        goals=0.4,
        lineup=1.0,
        availability=0.0,
        odds_support=0.0,
        model_signal=0.5,
    )

    assert set(
        snapshot
    ) == set(
        DEFAULT_FACTORS
    )

    assert snapshot["form"] == pytest.approx(
        0.1
    )

    assert snapshot["lineup"] == pytest.approx(
        1.0
    )


def test_market_learning_returns_safe_default():
    state = market_learning(
        {},
        "1x2",
    )

    assert isinstance(
        state,
        dict,
    )

    assert state.get(
        "total_samples",
        0,
    ) == 0

    assert state.get(
        "status"
    ) in {
        None,
        "collecting",
    }


def test_calibrated_confidence_is_bounded():
    state = market_learning(
        {},
        "1x2",
    )

    assert (
        0.0
        <= calibrated_confidence(
            75.0,
            state,
        )
        <= 100.0
    )


def test_build_learning_samples_creates_three_markets():
    prediction = _prediction()

    result = _result(
        home_goals=2,
        away_goals=1,
    )

    samples = build_learning_samples(
        [
            prediction
        ],
        [
            result
        ],
        delivered_only=False,
    )

    markets = {
        sample["market"]
        for sample in samples
    }

    assert markets == {
        "1x2",
        "ou25",
        "btts",
    }


def test_build_learning_samples_scores_correct_markets():
    prediction = _prediction(
        outcome="HOME",
        ou25="OVER",
        btts="YES",
    )

    result = _result(
        home_goals=2,
        away_goals=1,
    )

    samples = build_learning_samples(
        [
            prediction
        ],
        [
            result
        ],
        delivered_only=False,
    )

    by_market = {
        sample["market"]:
            sample
        for sample in samples
    }

    assert by_market[
        "1x2"
    ]["correct"] is True

    assert by_market[
        "ou25"
    ]["correct"] is True

    assert by_market[
        "btts"
    ]["correct"] is True


def test_build_learning_samples_learns_from_wrong_predictions():
    prediction = _prediction(
        outcome="AWAY",
        ou25="UNDER",
        btts="NO",
    )

    result = _result(
        home_goals=2,
        away_goals=1,
    )

    samples = build_learning_samples(
        [
            prediction
        ],
        [
            result
        ],
        delivered_only=False,
    )

    assert len(
        samples
    ) == 3

    assert all(
        sample["correct"] is False
        for sample in samples
    )


def test_build_learning_samples_can_filter_undelivered():
    prediction = _prediction(
        delivered=False
    )

    result = _result()

    samples = build_learning_samples(
        [
            prediction
        ],
        [
            result
        ],
        delivered_only=True,
    )

    assert samples == []


def test_learning_collects_below_20_samples():
    prediction = _prediction()
    result = _result()

    samples = []

    for index in range(
        10
    ):
        row = dict(
            prediction
        )

        row["fixture_id"] = str(
            index
        )

        result_row = dict(
            result
        )

        result_row["fixture_id"] = str(
            index
        )

        samples.extend(
            build_learning_samples(
                [
                    row
                ],
                [
                    result_row
                ],
                delivered_only=False,
            )
        )

    state, events = update_learning_state(
        {},
        samples,
        now=datetime.now(
            UTC
        ),
    )

    for market in (
        "1x2",
        "ou25",
        "btts",
    ):
        market_state = market_learning(
            state,
            market,
        )

        assert (
            market_state[
                "total_samples"
            ]
            == 10
        )

        assert market_state[
            "status"
        ] == "collecting_4_weeks"

    assert isinstance(
        events,
        list,
    )


def test_learning_state_preserves_model_weights():
    original = {
        "model_weights": {
            "poisson": 0.5,
            "elo": 0.5,
        },
    }

    state, _ = update_learning_state(
        original,
        [],
        now=datetime.now(
            UTC
        ),
    )

    assert state[
        "model_weights"
    ] == original[
        "model_weights"
    ]


def test_learning_weights_remain_bounded():
    now = datetime.now(
        UTC
    )

    factors = factor_snapshot(
        form=1.0,
        home_away=1.0,
        elo=1.0,
        goals=1.0,
        lineup=1.0,
        availability=1.0,
        odds_support=1.0,
        model_signal=1.0,
    )

    samples = []

    for index in range(
        40
    ):
        samples.append(
            {
                "fixture_id":
                    str(
                        index
                    ),
                "market":
                    "1x2",
                "correct":
                    False,
                "confidence":
                    90.0,
                "factors":
                    dict(
                        factors
                    ),
                "settled_at":
                    (
                        now
                        - timedelta(
                            minutes=index
                        )
                    ).isoformat(),
            }
        )

    state, _ = update_learning_state(
        {},
        samples,
        now=now,
    )

    market_state = market_learning(
        state,
        "1x2",
    )

    weights = market_state.get(
        "weights",
        {}
    )

    for factor, baseline in (
        DEFAULT_FACTORS.items()
    ):
        assert (
            baseline * 0.75
            <= weights[factor]
            <= baseline * 1.25
        )


def test_critical_error_rate_is_detected_after_30_samples():
    now = datetime.now(
        UTC
    )

    factors = factor_snapshot(
        form=0.5,
        home_away=0.18,
        elo=0.4,
        goals=0.3,
        lineup=1.0,
        availability=0.0,
        odds_support=0.0,
        model_signal=0.4,
    )

    samples = [
        {
            "fixture_id":
                str(
                    index
                ),
            "market":
                "1x2",
            "correct":
                False,
            "confidence":
                85.0,
            "factors":
                dict(
                    factors
                ),
            "settled_at":
                (
                    now
                    - timedelta(
                        minutes=index
                    )
                ).isoformat(),
        }
        for index in range(
            30
        )
    ]

    state, events = update_learning_state(
        {},
        samples,
        now=now,
    )

    market_state = market_learning(
        state,
        "1x2",
    )

    assert (
        market_state[
            "total_samples"
        ]
        >= 30
    )

    assert (
        market_state.get(
            "recent_30_error_rate",
            0.0,
        )
        >= 0.5
    )

    assert isinstance(
        events,
        list,
    )
