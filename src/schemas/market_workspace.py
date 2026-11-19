"""Market-qualified identities; syntax resolution never verifies a listing."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class InstrumentIdentity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    instrument_id: str
    market: Literal['cn','hk','us']
    symbol: str
    source_symbol: str
    timezone: str
    quote_currency: str | None = None
    financial_currency: str | None = None
    exchange: str = 'unknown'
    asset_type: str = 'unknown'
    issuer_id: str | None = None
    identity_verified: bool = False


MARKET_TIMEZONES={'cn':'Asia/Shanghai','hk':'Asia/Hong_Kong','us':'America/New_York'}
CODE_PATTERN=r'^(?:\d{6}|(?:us:[A-Z][A-Z0-9]*(?:[.\-][A-Z0-9]+)?)|(?:hk:\d{5}))$'
