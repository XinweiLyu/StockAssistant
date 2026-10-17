import pytest
from pydantic import ValidationError


def test_catalog_query_bounds_and_unknown_fields():
    from src.schemas.a_share_market import CatalogQuery
    assert CatalogQuery().page_size == 50
    for values in ({'page_size':101}, {'page':0}, {'sort':'arbitrary_sql'}):
        with pytest.raises(ValidationError):
            CatalogQuery(**values)


def test_chart_accepts_negative_adjusted_prices_but_rejects_invalid_ohlc():
    from src.schemas.a_share_market import MarketBar
    bar = dict(date='2026-10-09', open=-2, high=-1, low=-3, close=-1.5, volume=100, amount=None)
    assert MarketBar(**bar).close == -1.5
    for changes in ({'high':float('inf')}, {'date':'2026-02-30'}, {'low':0}, {'volume':-1}):
        with pytest.raises(ValidationError):
            MarketBar(**(bar | changes))


def test_date_range_is_not_silently_clipped_or_reversed():
    from src.schemas.a_share_market import history_dates
    assert history_dates('2025-10-09','2026-10-09') == ('2025-10-09','2026-10-09')
    for start,end in [('2026-10-10','2026-10-09'),('2010-01-01','2026-10-09')]:
        with pytest.raises(ValueError):
            history_dates(start,end)


def test_st_unknown_is_preserved_and_stock_codes_keep_zero():
    from src.schemas.a_share_market import MarketStock
    s=MarketStock(code='000001',name='目录样本',source='fixture',fetched_at='2026-10-09T15:00:00+08:00')
    assert s.code=='000001' and s.st is None and not s.identity_verified


def test_existing_settings_keep_limited_scope():
    from src.services.a_share_service import settings_from_saved
    assert settings_from_saved({'mode':'free','pool_size':40}).research_scope=='limited'
    assert settings_from_saved(None).research_scope=='all'
