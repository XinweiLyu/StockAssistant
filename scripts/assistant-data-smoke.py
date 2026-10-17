"""Read public free interfaces without touching portfolios or recommending trades."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_provider.a_share import CapabilityProvider

if '--market' in sys.argv:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from src.schemas.a_share import AssistantSettings
    from data_provider.a_share_market import MarketProvider
    provider=MarketProvider(CapabilityProvider(timeout=20),AssistantSettings(mode='free'))
    current=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    end=(current-timedelta(days=1)).isoformat()
    start=(current-timedelta(days=365)).isoformat()
    def probe(name,fn):
        try:
            value=fn()
            if hasattr(value,'items') and not isinstance(value,dict):
                result=dict(source=value.source,adjust=value.adjust,rows=len(value.items),start=value.actual_start or (value.items[0].date if value.items else None),end=value.actual_end or (value.items[-1].date if value.items else None),basis=value.adjustment_basis)
            else: result=dict(rows=len(value))
            print(json.dumps(dict(interface=name,status='ok',**result),ensure_ascii=False),flush=True)
            return value
        except (ValueError,RuntimeError) as exc:
            print(json.dumps(dict(interface=name,status='failed',error=str(exc)[:180]),ensure_ascii=False),flush=True)
            return None
    probe('all-market-snapshot',provider.quotes)
    for exchange,board in [('SSE','main'),('SSE','star'),('SZSE','main'),('BSE','beijing')]:
        probe('directory:'+exchange+':'+board,lambda e=exchange,b=board:provider.listing_slice(e,b))
    probe('benchmark-independent',lambda:provider.benchmark_history(start,end,'akshare/tencent'))
    for code in ['600000','300750','688981','920002']:
        for adjust in ['raw','qfq']:
            probe('history:'+code+':'+adjust,lambda c=code,a=adjust:provider.history(c,start,end,a,source='akshare/tencent'))
    for kind in ['industry','concept']:
        sectors=probe('sectors:'+kind,lambda k=kind:provider.sectors(k))
        if sectors:
            sector=sectors[0].model_dump()
            probe('members:'+sector['sector_id'],lambda:provider.members(sector))
            probe('sector-history:'+sector['sector_id'],lambda:provider.sector_history(sector,start,end))
    probe('benchmark',lambda:provider.benchmark_history(start,end,'akshare/tencent'))
    sys.exit(0)

provider=CapabilityProvider(timeout=40)
queries=[('tool_trade_date_hist_sina',{}),('stock_info_global_em',{}),('stock_zh_a_spot_em',{})]
if '--extended' in sys.argv:
    queries=[('stock_zh_a_spot_tx',{}),('stock_zh_a_daily',dict(symbol='sh600000',start_date='20260101',end_date='20261009',adjust='')),('stock_info_sh_name_code',dict(symbol='主板A股')),('stock_zh_a_hist_tx',dict(symbol='sh600000',start_date='20260101',end_date='20261009',adjust='qfq',timeout=20))]
for name,params in queries:
    try:
        rows=provider.call(name,params)
        print(json.dumps(dict(interface=name,status='ok',rows=len(rows),fields=list(rows[0]) if rows else [],sample=rows[:1] if '--extended' in sys.argv else None,
                              calendar_end=max(str(r.get('trade_date',''))[:10] for r in rows) if name.startswith('tool_') and rows else None),ensure_ascii=False),flush=True)
    except (ValueError,RuntimeError) as exc:
        print(json.dumps(dict(interface=name,status='failed',error=str(exc)),ensure_ascii=False),flush=True)
