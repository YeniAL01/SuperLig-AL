"""Prediction service timing and delivery tests."""

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace

import pytest

from app.models import Fixture, Prediction
from app.service import PredictionService


class FakeCollector:
    def __init__(
        self,
        fixtures=None,
        results=None,
        lineup_verified=False,
    ):
        self._fixtures = fixtures or []
        self._results = results or []
        self.lineup_verified = lineup_verified
        self.match_calls = []

    def fixtures(
        self,
        league_id,
    ):
        return list(
            self._fixtures
        )

    def results(
        self,
        league_id,
    ):
        return list(
            self._results
        )

    def match(
        self,
        fixture_id,
    ):
        self.match_calls.append(
            fixture_id
        )

        starters = (
            [
                {
                    "id": index,
                    "name": f"Player {index}",
                }
                for index in range(
                    1,
                    12,
                )
            ]
            if self.lineup_verified
            else []
        )

        return {
            "content": {
                "lineup": {
                    "homeTeam": {
                        "starters":
                            list(
                                starters
                            ),
                    },
                    "awayTeam": {
                        "starters":
                            list(
                                starters
                            ),
                    },
                },
            },
        }


def settings(
    tmp_path,
):
    return SimpleNamespace(
        data_dir=tmp_path,
        league_id=71,
        minimum_probability=0.0,
        prediction_token="",
        prediction_chat_id="",
    )


def service(
    tmp_path,
    collector,
):
    return PredictionService(
        settings(
            tmp_path
        ),
        collector,
        logging.getLogger(
            "test-service"
        ),
    )


def future_fixture(
    minutes,
    fixture_id=1,
):
    return Fixture(
        fixture_id,
        f"Ev {fixture_id}",
        f"Dep {fixture_id}",
        datetime.now(
            UTC
        )
        + timedelta(
            minutes=minutes
        ),
    )


def read_analysis(
    prediction_service,
):
    return prediction_service.store.read(
        "pre_match_analysis",
        {},
    )


def test_outside_t60_does_not_request_lineup(
    tmp_path,
):
    collector = FakeCollector(
        fixtures=[
            future_fixture(
                180
            )
        ]
    )

    prediction_service = service(
        tmp_path,
        collector,
    )

    prediction_service.run()

    assert collector.match_calls == []

    assert read_analysis(
        prediction_service
    ) == {}


def _fake_prediction(fixture):
    class FakePrediction:
        data_quality = 1.0
        confidence = 80.0
        lineup_verified = False
        markets = {}

        def payload(self):
            return {
                "fixture_id": fixture.id,
                "fixture": f"{fixture.home} - {fixture.away}",
                "kickoff": fixture.start.isoformat(),
                "confidence": self.confidence,
                "data_quality": self.data_quality,
            }

    return FakePrediction()


def test_first_lineup_attempt_waits_when_missing(tmp_path, monkeypatch):
    fixture = future_fixture(55)
    collector = FakeCollector(fixtures=[fixture], lineup_verified=False)
    prediction_service = service(tmp_path, collector)
    built = []
    monkeypatch.setattr(prediction_service, "_build", lambda fixture, analysis_state=None: built.append(fixture.id) or _fake_prediction(fixture))

    prediction_service.run()

    state = read_analysis(prediction_service)[str(fixture.id)]
    assert collector.match_calls == [fixture.id]
    assert state["lineup_attempts"] == 1
    assert state["lineup_verified"] is False
    assert state["lineup_fallback"] is False
    assert built == []


def test_verified_lineup_builds_immediately(tmp_path, monkeypatch):
    fixture = future_fixture(55)
    collector = FakeCollector(fixtures=[fixture], lineup_verified=True)
    prediction_service = service(tmp_path, collector)
    built = []
    monkeypatch.setattr(prediction_service, "_build", lambda fixture, analysis_state=None: built.append(fixture.id) or _fake_prediction(fixture))

    count = prediction_service.run()

    state = read_analysis(prediction_service)[str(fixture.id)]
    assert state["lineup_attempts"] == 1
    assert state["lineup_verified"] is True
    assert state["lineup_fallback"] is False
    assert built == [fixture.id]
    assert count == 1


def test_lineup_retry_requires_ten_minutes(tmp_path, monkeypatch):
    fixture = future_fixture(55)
    collector = FakeCollector(fixtures=[fixture], lineup_verified=False)
    prediction_service = service(tmp_path, collector)
    monkeypatch.setattr(prediction_service, "_build", lambda fixture, analysis_state=None: _fake_prediction(fixture))

    prediction_service.run()
    prediction_service.run()

    state = read_analysis(prediction_service)[str(fixture.id)]
    assert collector.match_calls == [fixture.id]
    assert state["lineup_attempts"] == 1


def test_third_missing_lineup_enables_fallback_and_builds(tmp_path, monkeypatch):
    fixture = future_fixture(40)
    collector = FakeCollector(fixtures=[fixture], lineup_verified=False)
    prediction_service = service(tmp_path, collector)
    built = []
    monkeypatch.setattr(prediction_service, "_build", lambda fixture, analysis_state=None: built.append(fixture.id) or _fake_prediction(fixture))

    # Seed two previous checks far enough in the past so this run is the third.
    prediction_service.store.write(
        "pre_match_analysis",
        {
            str(fixture.id): {
                "fixture_id": fixture.id,
                "fixture": f"{fixture.home} - {fixture.away}",
                "home_team": fixture.home,
                "away_team": fixture.away,
                "kickoff": fixture.start.isoformat(),
                "analysis_started_at": (datetime.now(UTC) - timedelta(minutes=25)).isoformat(),
                "lineup_verified": False,
                "lineup_verified_at": None,
                "lineup_attempts": 2,
                "last_lineup_check_at": (datetime.now(UTC) - timedelta(minutes=10, seconds=5)).isoformat(),
                "lineup_fallback": False,
                "lineup_fallback_at": None,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        },
    )

    count = prediction_service.run()

    state = read_analysis(prediction_service)[str(fixture.id)]
    assert collector.match_calls == [fixture.id]
    assert state["lineup_attempts"] == 3
    assert state["lineup_verified"] is False
    assert state["lineup_fallback"] is True
    assert built == [fixture.id]
    assert count == 1


def seed_two_attempts(prediction_service, fixtures):
    state = {}
    stamp = datetime.now(UTC) - timedelta(minutes=11)
    for fixture in fixtures:
        state[str(fixture.id)] = {
            "fixture_id": fixture.id,
            "fixture": f"{fixture.home} - {fixture.away}",
            "home_team": fixture.home,
            "away_team": fixture.away,
            "kickoff": fixture.start.isoformat(),
            "analysis_started_at": (stamp - timedelta(minutes=10)).isoformat(),
            "lineup_verified": False,
            "lineup_verified_at": None,
            "lineup_attempts": 2,
            "last_lineup_check_at": stamp.isoformat(),
            "lineup_fallback": False,
            "lineup_fallback_at": None,
            "updated_at": stamp.isoformat(),
        }
    prediction_service.store.write("pre_match_analysis", state)


def test_manual_run_does_not_bypass_timing(
    tmp_path,
):
    fixture = future_fixture(
        120
    )

    collector = FakeCollector(
        fixtures=[
            fixture
        ]
    )

    prediction_service = service(
        tmp_path,
        collector,
    )

    prediction_service.run()

    assert collector.match_calls == []

    assert (
        prediction_service.store.read(
            "forecasts",
            [],
        )
        == []
    )

    assert (
        prediction_service.store.read(
            "predictions",
            [],
        )
        == []
    )

    assert (
        prediction_service.store.read(
            "delivery",
            {},
        )
        == {}
    )


def test_same_time_fixtures_are_all_processed(
    tmp_path,
    monkeypatch,
):
    kickoff = (
        datetime.now(
            UTC
        )
        + timedelta(
            minutes=10
        )
    )

    fixtures = [
        Fixture(
            101,
            "Ev 101",
            "Dep 101",
            kickoff,
        ),
        Fixture(
            102,
            "Ev 102",
            "Dep 102",
            kickoff,
        ),
    ]

    collector = FakeCollector(
        fixtures=fixtures,
        lineup_verified=False,
    )

    prediction_service = service(
        tmp_path,
        collector,
    )

    built = []

    class FakePrediction:
        data_quality = 1.0
        confidence = 80.0

        def __init__(
            self,
            fixture,
        ):
            self.fixture = fixture

        def payload(
            self,
        ):
            return {
                "fixture_id":
                    self.fixture.id,
                "fixture":
                    (
                        f"{self.fixture.home} - "
                        f"{self.fixture.away}"
                    ),
                "kickoff":
                    self.fixture.start.isoformat(),
                "confidence":
                    self.confidence,
                "data_quality":
                    self.data_quality,
            }

    def fake_build(
        fixture,
        analysis_state=None,
    ):
        built.append(
            fixture.id
        )

        return FakePrediction(
            fixture
        )

    monkeypatch.setattr(
        prediction_service,
        "_build",
        fake_build,
    )

    seed_two_attempts(prediction_service, fixtures)

    count = (
        prediction_service.run()
    )

    assert count == 2

    assert built == [
        101,
        102,
    ]

    delivery = (
        prediction_service.store.read(
            "delivery",
            {},
        )
    )

    assert set(
        delivery
    ) == {
        "101",
        "102",
    }

    assert all(
        state["status"]
        == "attempting"
        for state
        in delivery.values()
    )


def test_third_attempt_build_does_not_require_verified_lineup(
    tmp_path,
    monkeypatch,
):
    fixture = future_fixture(10)
    collector = FakeCollector(fixtures=[fixture], lineup_verified=False)
    prediction_service = service(tmp_path, collector)
    captured = {}

    class FakePrediction:
        data_quality = 1.0
        confidence = 80.0
        lineup_verified = False
        markets = {"1x2": {}, "ou25": {}, "btts": {}}
        def payload(self):
            return {
                "fixture_id": fixture.id,
                "fixture": f"{fixture.home} - {fixture.away}",
                "kickoff": fixture.start.isoformat(),
                "confidence": self.confidence,
                "data_quality": self.data_quality,
                "lineup_verified": self.lineup_verified,
            }

    def fake_predict(self, target_fixture, home, away, lineup_verified=False, as_of=None):
        captured["lineup_verified"] = lineup_verified
        return FakePrediction()

    monkeypatch.setattr("app.service.forms", lambda *args, **kwargs: (SimpleNamespace(), SimpleNamespace()))
    monkeypatch.setattr("app.service.PredictionEngine.predict", fake_predict)
    seed_two_attempts(prediction_service, [fixture])

    prediction_service.run()

    assert collector.match_calls == [fixture.id]
    assert captured["lineup_verified"] is False
    state = read_analysis(prediction_service)[str(fixture.id)]
    assert state["lineup_attempts"] == 3
    assert state["lineup_fallback"] is True


@pytest.mark.parametrize(
    (
        "minutes",
        "expected_match_calls",
    ),
    [
        (
            61,
            0,
        ),
        (
            45,
            1,
        ),
        (
            31,
            1,
        ),
        (
            29,
            1,
        ),
        (
            20,
            1,
        ),
    ],
)
def test_lineup_polling_boundaries(
    tmp_path,
    minutes,
    expected_match_calls,
):
    fixture = future_fixture(
        minutes
    )

    collector = FakeCollector(
        fixtures=[
            fixture
        ],
        lineup_verified=False,
    )

    prediction_service = service(
        tmp_path,
        collector,
    )

    prediction_service.run()

    assert len(
        collector.match_calls
    ) == expected_match_calls

@pytest.mark.parametrize(
    ('confidence', 'data_quality'),
    [(47.41, 1.0), (80.0, 0.2), (47.41, 0.0)],
)
def test_final_prediction_is_reserved_and_delivered_below_thresholds(
    tmp_path, monkeypatch, confidence, data_quality,
):
    fixture = future_fixture(10)
    collector = FakeCollector(fixtures=[fixture])
    prediction_service = service(tmp_path, collector)
    prediction_service.settings.minimum_probability = 58.0
    prediction_service.settings.prediction_token = 'test-token'
    prediction_service.settings.prediction_chat_id = 'test-chat'
    prediction = Prediction(
        fixture_id=fixture.id,
        fixture=f'{fixture.home} - {fixture.away}',
        winner=fixture.home,
        home_goals=2,
        away_goals=1,
        confidence=confidence,
        lineup_verified=False,
        kickoff=fixture.start.isoformat(),
        home_team=fixture.home,
        away_team=fixture.away,
        outcome='HOME',
        data_quality=data_quality,
        markets={
            '1x2': {'selection': 'HOME', 'confidence': confidence},
            'ou25': {'selection': 'OVER', 'confidence': 55.2},
            'btts': {'selection': 'YES', 'confidence': 51.3},
        },
    )
    monkeypatch.setattr(prediction_service, '_build', lambda *args: prediction)
    seed_two_attempts(prediction_service, [fixture])
    messages = []

    def fake_send_photo(client, image, caption):
        # The real formatter runs, but no request reaches Telegram.
        assert prediction_service.store.read('delivery', {})[str(fixture.id)]['status'] == 'attempting'
        messages.append(image.read_bytes())
        return True

    monkeypatch.setattr('app.service.TelegramClient.send_photo', fake_send_photo)
    assert prediction_service.run() == 1
    forecasts = prediction_service.store.read('forecasts', [])
    assert forecasts == [{**prediction.payload(), 'publishable': True}]
    assert prediction_service.store.read('predictions', []) == [prediction.payload()]
    reservation = prediction_service.store.read('delivery', {})
    assert reservation[str(fixture.id)]['status'] == 'attempting'
    assert messages == []

    # Re-running before delivery keeps the immutable forecast/reservation.
    assert prediction_service.run() == 0
    assert prediction_service.store.read('delivery', {}) == reservation
    assert prediction_service.store.read('forecasts', []) == forecasts
    assert prediction_service.deliver() == 0
    assert len(messages) == 1
    assert messages[0].startswith(b'\x89PNG')
    assert prediction_service.store.read('delivery', {})[str(fixture.id)]['status'] == 'delivered'

    # Successfully delivered predictions cannot be sent again.
    assert prediction_service.run() == 0
    assert prediction_service.deliver() == 0
    assert len(messages) == 1


def test_real_engine_final_prediction_with_no_history_is_publishable(tmp_path):
    prediction_service = service(tmp_path, FakeCollector(fixtures=[future_fixture(10)]))
    prediction_service.settings.minimum_probability = 58.0
    seed_two_attempts(prediction_service, prediction_service.collector._fixtures)
    assert prediction_service.run() == 1
    forecast, = prediction_service.store.read('forecasts', [])
    assert forecast['confidence'] < 58.0
    assert forecast['data_quality'] == 0.0
    assert forecast['publishable'] is True
    assert len(prediction_service.store.read('predictions', [])) == 1
    assert prediction_service.store.read('delivery', {})[str(forecast['fixture_id'])]['status'] == 'attempting'

@pytest.mark.parametrize('first_success', [True, False])
def test_grouped_photo_delivery_and_retry(tmp_path, monkeypatch, first_success):
    fixtures = [future_fixture(10, 101), future_fixture(10, 102)]
    svc = service(tmp_path, FakeCollector(fixtures=fixtures))
    svc.settings.prediction_token = 'test-token'
    svc.settings.prediction_chat_id = 'test-chat'
    seed_two_attempts(svc, fixtures)
    assert svc.run() == 2
    photos = []

    def send_photo(client, image, caption):
        states = svc.store.read('delivery', {})
        assert all(states[str(f.id)]['status'] == 'attempting' for f in fixtures)
        photos.append(image.read_bytes())
        return first_success if len(photos) == 1 else True

    monkeypatch.setattr('app.service.TelegramClient.send_photo', send_photo)
    assert svc.deliver() == (0 if first_success else 1)
    assert len(photos) == 1
    expected = 'delivered' if first_success else 'failed'
    assert all(s['status'] == expected for s in svc.store.read('delivery', {}).values())
    assert svc.run() == 0
    assert svc.deliver() == 0
    assert len(photos) == (1 if first_success else 2)
    assert all(s['status'] == 'delivered' for s in svc.store.read('delivery', {}).values())
    assert svc.deliver() == 0
    assert len(photos) == (1 if first_success else 2)


def test_expired_reservation_is_excluded_from_group(tmp_path, monkeypatch):
    svc = service(tmp_path, FakeCollector(fixtures=[future_fixture(10, 101), future_fixture(10, 102)]))
    svc.settings.prediction_token = 'test'
    svc.settings.prediction_chat_id = 'test'
    seed_two_attempts(svc, svc.collector._fixtures)
    assert svc.run() == 2
    rows = svc.store.read('predictions', [])
    rows[0]['kickoff'] = (datetime.now(UTC)-timedelta(minutes=1)).isoformat()
    svc.store.write('predictions', rows)
    sent = []
    monkeypatch.setattr('app.service.TelegramClient.send_predictions', lambda client, batch: sent.extend(batch) or True)
    assert svc.deliver() == 1
    assert [p.fixture_id for p in sent] == [102]
    states = svc.store.read('delivery', {})
    assert states['101']['status'] == 'expired'
    assert states['102']['status'] == 'delivered'
