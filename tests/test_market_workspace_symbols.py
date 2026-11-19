import pytest


@pytest.mark.parametrize('market,symbol,key,source', [
    ('hk','hk00700','hk:00700','0700.HK'),('hk','00700','hk:00700','0700.HK'),
    ('hk','0700.HK','hk:00700','0700.HK'),('us','aapl','us:AAPL','AAPL'),
    ('us','BRK.B','us:BRK.B','BRK-B'),('us','BRK-B','us:BRK.B','BRK-B'),
    ('cn','000807','cn:000807','000807.SZ'),
])
def test_qualified_identity(market,symbol,key,source):
    from src.services.market_workspace_symbols import resolve_instrument
    identity=resolve_instrument(market,symbol)
    assert identity.instrument_id==key
    assert identity.source_symbol==source
    assert identity.identity_verified is False


@pytest.mark.parametrize('market,symbol',[('us','00700'),('hk','AAPL'),('cn','hk00700'),('hk','us:AAPL'),('us','A/B'),('us','^GSPC')])
def test_reject_conflicting_or_nonstock_input(market,symbol):
    from src.services.market_workspace_symbols import resolve_instrument
    with pytest.raises(ValueError):resolve_instrument(market,symbol)


def test_offshore_snapshot_requires_explicit_currency():
    from src.schemas.a_share_value import ValueSnapshot
    with pytest.raises(ValueError):
        ValueSnapshot(snapshot_id='s',code='us:AAPL',name='Apple',cutoff='2026-11-16T00:00:00+00:00')
    valid=ValueSnapshot(snapshot_id='s',code='us:AAPL',market='us',currency='USD',name='Apple',cutoff='2026-11-16T00:00:00+00:00')
    assert valid.market=='us' and valid.currency=='USD'


def test_legacy_snapshot_keeps_default_currency():
    from src.schemas.a_share_value import ValueSnapshot
    item=ValueSnapshot(snapshot_id='s',code='000807',name='云铝',cutoff='2026-11-16T00:00:00+00:00')
    assert item.market=='cn' and item.currency=='CNY'
