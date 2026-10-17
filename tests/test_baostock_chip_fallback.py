"""Regression coverage for free chip estimates when Eastmoney CYQ is unavailable."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from data_provider.base import DataFetcherManager
from data_provider.baostock_fetcher import BaostockFetcher
from data_provider.chip_distribution import calculate_chip_distribution
from data_provider.realtime_types import get_chip_circuit_breaker


def _flat_bars(count=210, price="10.00", turn="2.0"):
    return [
        {"date": (date.today() - timedelta(days=count - 1 - i)).isoformat(),
         "open": price, "high": price, "low": price, "close": price,
         "turn": turn, "tradestatus": "1"}
        for i in range(count)
    ]


def test_flat_price_history_produces_valid_bounded_chip_estimate():
    chip = calculate_chip_distribution("000807", _flat_bars())
    assert chip is not None
    assert chip.source == "baostock/estimated_cyq"
    assert chip.date == _flat_bars()[-1]["date"]
    assert chip.avg_cost == 10.0
    assert chip.profit_ratio == 1.0
    assert chip.cost_90_low == chip.cost_90_high == 10.0
    assert chip.cost_70_low == chip.cost_70_high == 10.0
    assert chip.concentration_90 == chip.concentration_70 == 0.0


def test_incomplete_or_invalid_history_is_not_misreported_as_valid_chips():
    assert calculate_chip_distribution("000807", _flat_bars(15)) is None
    assert calculate_chip_distribution("000807", _flat_bars(turn="")) is None
    assert calculate_chip_distribution("000807", _flat_bars(price="0")) is None


def test_manager_uses_baostock_fallback_after_akshare_failure():
    from data_provider.akshare_fetcher import AkshareFetcher
    get_chip_circuit_breaker().reset()
    ak = AkshareFetcher()
    baostock = BaostockFetcher()
    manager = DataFetcherManager(fetchers=[ak, baostock])
    with patch("src.config.get_config", return_value=SimpleNamespace(enable_chip_distribution=True)), \
         patch.object(ak, "get_chip_distribution", return_value=None), \
         patch("data_provider.akshare_fetcher._akshare_call_with_timeout", return_value=_flat_bars()):
        chip = manager.get_chip_distribution("000807.SZ")
    assert chip is not None
    assert chip.code == "000807"
    assert chip.avg_cost == 10.0
    assert chip.source == "baostock/estimated_cyq"


def test_baostock_chip_fallback_skips_etf_and_bse():
    fetcher = BaostockFetcher()
    with patch("data_provider.akshare_fetcher._akshare_call_with_timeout") as worker:
        assert fetcher.get_chip_distribution("512400") is None
        assert fetcher.get_chip_distribution("920002") is None
    worker.assert_not_called()


def test_data_only_chip_endpoint_returns_estimate_without_analysis(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.v1.endpoints import a_share

    result = calculate_chip_distribution("000807", _flat_bars())
    class Manager:
        def get_chip_distribution(self, code):
            assert code == "000807"
            return result

    monkeypatch.setattr(a_share, "DataFetcherManager", Manager)
    a_share._chip_cache.clear()
    app = FastAPI()
    app.include_router(a_share.router)
    client = TestClient(app)
    response = client.get("/chip/000807")
    assert response.status_code == 200
    assert response.json()["chip"]["source"] == "baostock/estimated_cyq"
    assert response.json()["chip"]["avg_cost"] == 10.0
    assert client.get("/chip/AAPL").status_code == 422
    a_share._chip_cache.clear()
