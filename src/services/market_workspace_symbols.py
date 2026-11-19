"""Normalize user codes only within an explicitly selected market."""
import re
from src.schemas.market_workspace import InstrumentIdentity, MARKET_TIMEZONES


def resolve_instrument(market: str, symbol: str) -> InstrumentIdentity:
    if market not in MARKET_TIMEZONES:raise ValueError('仅支持A股、港股和美股')
    code=str(symbol or '').strip().upper()
    if ':' in code:
        prefix,code=code.split(':',1)
        if prefix.lower()!=market:raise ValueError('证券代码与所选市场不一致')
    if market=='cn':
        if not re.fullmatch(r'\d{6}',code):raise ValueError('A股须使用六位代码')
        source=code+('.SS' if code.startswith('6') else '.BJ' if code.startswith(('4','8','9')) else '.SZ')
    elif market=='hk':
        if code.startswith('HK'):code=code[2:]
        if code.endswith('.HK'):code=code[:-3]
        if not re.fullmatch(r'\d{1,5}',code) or int(code)==0:raise ValueError('港股须使用1至5位代码或.HK代码')
        code=code.zfill(5);source=code[-4:]+'.HK' if code.startswith('0') else code+'.HK'
    else:
        if not re.fullmatch(r'[A-Z][A-Z0-9]{0,9}(?:[.\-][A-Z0-9]{1,3})?',code):raise ValueError('美股代码格式不正确')
        # Class-share notation belongs to the listing identity; Yahoo spelling is separate.
        code=code.replace('-','.')
        source=code.replace('.','-')
    return InstrumentIdentity(instrument_id=market+':'+code,market=market,symbol=code,
        source_symbol=source,timezone=MARKET_TIMEZONES[market])
