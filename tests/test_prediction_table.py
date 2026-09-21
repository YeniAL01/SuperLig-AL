from types import SimpleNamespace
from dataclasses import replace
import pytest
from PIL import Image
from app.models import Prediction
from telegram.client import TelegramClient
from reporting.prediction_table import create_prediction_table


def example():
    return Prediction(1, 'Galatasaray - Fenerbahçe', 'Galatasaray', 2, 1, 62.5, True,
        home_team='Galatasaray', away_team='Fenerbahçe', outcome='HOME', kickoff='2026-10-10T17:00:00+00:00',
        markets={'1x2': {'selection': 'HOME', 'confidence': 62.5},
                 'ou25': {'selection': 'OVER', 'confidence': 68.2},
                 'btts': {'selection': 'YES', 'confidence': 64.7}})


def test_prediction_rows_only_expose_public_markets(tmp_path):
    client=TelegramClient('test','test'); rows=client.prediction_rows([example()])
    assert rows[0]['fixture']=='Galatasaray - Fenerbahçe'
    assert rows[0]['winner']=='Galatasaray'
    assert rows[0]['ou25']=='ÜST'
    assert rows[0]['confidence']==62.5
    assert 'btts' not in rows[0] and 'score' not in rows[0]
    path=create_prediction_table(rows,tmp_path/'cards.png')
    with Image.open(path) as image:
        assert image.width==1400


@pytest.mark.parametrize('body,ok,expected',[({'ok':True},True,True),({'ok':False},True,False),({'ok':True},False,False),([],True,False)])
def test_photo_delivery_requires_api_confirmation(tmp_path,monkeypatch,body,ok,expected):
    path=tmp_path/'test.png'; path.write_bytes(b'png')
    monkeypatch.setattr('telegram.client.requests.post',lambda *a,**kw:SimpleNamespace(ok=ok,json=lambda:body))
    assert TelegramClient('test','test').send_photo(path,'test') is expected


def test_predictions_are_split_into_four_card_images():
    predictions=[replace(example(),fixture_id=i) for i in range(9)]
    batches=list(TelegramClient('test','test').prediction_batches(predictions))
    assert [len(x) for x in batches]==[4,4,1]
