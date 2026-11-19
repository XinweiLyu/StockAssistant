"""Opt-in free-data smoke test; never calls a language model.

RUN_MARKET_WORKSPACE_NETWORK=1 python -m pytest -q -m network tests/test_market_workspace_network.py
"""
import os
from datetime import datetime,timedelta,timezone
import pytest
from data_provider.market_workspace import WorkspaceProvider
from src.services.market_workspace_symbols import resolve_instrument

pytestmark=[pytest.mark.network,pytest.mark.skipif(os.getenv('RUN_MARKET_WORKSPACE_NETWORK')!='1',reason='opt-in real public data')]


@pytest.mark.parametrize('market,symbol',[('us','AAPL'),('us','MSFT'),('hk','00700'),('hk','01810')])
def test_public_identity_and_paired_history(market,symbol):
    provider=WorkspaceProvider();identity=resolve_instrument(market,symbol)
    metadata=provider.identity(identity)
    assert metadata['verified'] and metadata['currency']
    end=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo(identity.timezone)).date()
    pair=provider.history(identity,(end-timedelta(days=25)).isoformat(),end.isoformat())
    assert pair['raw'] and pair['adjusted']
    assert [r['date'] for r in pair['raw']]==[r['date'] for r in pair['adjusted']]
    assert pair['basis'] and pair['fetched_at']
