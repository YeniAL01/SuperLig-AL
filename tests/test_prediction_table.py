from types import SimpleNamespace
from dataclasses import replace
import pytest
from PIL import Image
from app.models import Prediction
from telegram.client import TelegramClient
from reporting.prediction_table import create_prediction_table, BLUE, RED


def example():
    return Prediction(1, 'Galatasaray - Fenerbahçe', 'Galatasaray', 2, 1, 62.5, True,
        home_team='Galatasaray', away_team='Fenerbahçe', outcome='HOME',
        markets={'1x2': {'selection': 'HOME', 'confidence': 62.5},
                 'ou25': {'selection': 'OVER', 'confidence': 68.2},
                 'btts': {'selection': 'YES', 'confidence': 64.7}})


def test_image_rows_preserve_market_confidences_and_lineup(tmp_path):
    client = TelegramClient('test', 'test')
    rows = client.prediction_rows([example(), replace(example(), fixture_id=2, lineup_verified=False)])
    assert rows[0] == ('Galatasaray - Fenerbahçe', 'Galatasaray Kazanır', '%62.5',
                       '2,5 Üst (%68.2)', 'Var (%64.7)', '2-1', True)
    assert rows[1][-1] is False
    path = create_prediction_table(rows, tmp_path/'table.png')
    with Image.open(path) as image:
        assert image.size == (1900, 640)
        for box, color in [((1554, 251, 1824, 379), BLUE), ((1554, 379, 1824, 507), RED)]:
            expected = tuple(bytes.fromhex(color[1:]))
            assert expected in set(image.crop(box).getdata())


@pytest.mark.parametrize('body,ok,expected', [({'ok': True}, True, True), ({'ok': False}, True, False), ({'ok': True}, False, False), ([], True, False)])
def test_photo_delivery_requires_api_confirmation(tmp_path, monkeypatch, body, ok, expected):
    path = tmp_path/'test.png'
    path.write_bytes(b'png')
    monkeypatch.setattr('telegram.client.requests.post', lambda *a, **kw: SimpleNamespace(ok=ok, json=lambda: body))
    assert TelegramClient('test', 'test').send_photo(path, 'test') is expected


def test_full_round_fits_one_image_batch():
    predictions = [replace(example(), fixture_id=i) for i in range(9)]
    assert list(TelegramClient('test', 'test').prediction_batches(predictions)) == [predictions]
