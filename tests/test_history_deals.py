import pytest
from unittest.mock import patch, MagicMock
from typing import Generator
from mt5_bridge.client import BridgeClient
from mt5_bridge.main import parse_datetime

def test_parse_datetime() -> None:
    """日付文字列およびタイムスタンプ文字列のパース処理をテストします。"""
    # 数値形式のタイムスタンプ文字列のパース
    assert parse_datetime("1704067200") == 1704067200
    
    # 日付文字列（UTC）のパース
    # 2024-01-01 00:00:00 UTC は 1704067200 になるはず
    assert parse_datetime("2024-01-01 00:00:00") == 1704067200


@patch("httpx.get")
def test_client_get_history_deals(mock_get: MagicMock) -> None:
    """BridgeClient の get_history_deals が正しく HTTP GET リクエストを送信し、結果を取得できるかテストします。"""
    # レスポンスのモック設定
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {
            "ticket": 12345,
            "order": 67890,
            "time": 1704067200,
            "time_msc": 1704067200000,
            "type": "BUY",
            "entry": "IN",
            "position_id": 111,
            "volume": 0.1,
            "price": 2000.0,
            "commission": -0.5,
            "swap": 0.0,
            "profit": 10.0,
            "comment": "test trade",
            "magic": 123456,
            "symbol": "XAUUSD"
        }
    ]
    mock_get.return_value = mock_resp

    # クライアントの初期化と実行
    client = BridgeClient("http://localhost:8000")
    result = client.get_history_deals(
        position=111,
        ticket=12345,
        start=1704067200,
        end=1704067300
    )

    # 正しいURLとパラメータでGETリクエストが送信されたことを検証
    mock_get.assert_called_once_with(
        "http://localhost:8000/history/deals",
        params={
            "position": 111,
            "ticket": 12345,
            "start": 1704067200,
            "end": 1704067300
        },
        timeout=30.0
    )
    
    # 戻り値の検証
    assert len(result) == 1
    assert result[0]["ticket"] == 12345
    assert result[0]["symbol"] == "XAUUSD"
    assert result[0]["profit"] == 10.0
