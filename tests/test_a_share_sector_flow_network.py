"""Opt-in free-source probes; never load .env or invoke a model."""
import os
import pytest
pytestmark=[pytest.mark.network,pytest.mark.skipif(os.getenv('RUN_SECTOR_FLOW_NETWORK')!='1',reason='opt-in upstream probe')]

def test_real_bk_history_preserves_code_date_and_units():
 from data_provider.a_share import CapabilityProvider
 from data_provider.a_share_sector_flow import normalize_history
 from tests.test_a_share_sector_flow_service import BOARD
 from datetime import datetime,timezone
 raw=CapabilityProvider().call('sector_fund_flow_history_em',dict(symbol='BK0478'))
 rows=normalize_history(raw,BOARD,datetime.now(timezone.utc).isoformat())
 assert len(rows)>=60 and all(r['sector_id']==BOARD['sector_id'] and r['unit']=='CNY' for r in rows)

def test_real_sector_rank_is_complete_and_typed():
 from data_provider.a_share import CapabilityProvider
 from data_provider.a_share_sector_flow import normalize_rank
 from datetime import datetime,timezone
 raw=CapabilityProvider().call('sector_fund_flow_rank_em',dict(kind='industry'))
 assert normalize_rank(raw,'industry',datetime.now(timezone.utc).isoformat())
