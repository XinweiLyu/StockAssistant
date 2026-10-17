"""Structured estimates remain separate from rule plans and account limits."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Price = float
class PriceModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class PriceContext(PriceModel):
    code: str = Field(pattern=r'^(\d{6}|DEMO\d{3})$')
    anchor_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    reference_price: Price = Field(gt=0, strict=True)
    currency: Literal['CNY'] = 'CNY'
    price_basis: Literal['raw'] = 'raw'
    data_hash: str
    adjustment_basis: str
    features: dict = Field(default_factory=dict)
    raw_anchor: float | None = None
    qfq_anchor: float | None = None
    source: str | None = None
    demo: bool = False

class AITradeLevels(PriceModel):
    horizon_sessions: Literal[5,10,20]
    entry_low: Price = Field(gt=0, strict=True)
    entry_high: Price = Field(gt=0, strict=True)
    stop_reference: Price = Field(gt=0, strict=True)
    sell_low: Price = Field(gt=0, strict=True)
    sell_high: Price = Field(gt=0, strict=True)
    conditions: list[str] = Field(min_length=1,max_length=8)
    invalidation: list[str] = Field(min_length=1,max_length=8)
    sources: list[str] = Field(min_length=1,max_length=12)
    @model_validator(mode='after')
    def ordered(self):
        if not self.stop_reference < self.entry_low <= self.entry_high < self.sell_low <= self.sell_high:
            raise ValueError('invalid price ordering')
        return self

class PriceForecast(PriceModel):
    scenario: Literal['bear','base','bull']
    horizon_sessions: Literal[5,10,20]
    low: Price = Field(gt=0, strict=True)
    high: Price = Field(gt=0, strict=True)
    conditions: list[str] = Field(min_length=1,max_length=8)
    sources: list[str] = Field(min_length=1,max_length=12)
    @model_validator(mode='after')
    def ordered(self):
        if self.low > self.high: raise ValueError('inverted forecast')
        return self

class PriceScenarioResult(PriceModel):
    context: PriceContext
    trade_levels: AITradeLevels | None = None
    forecasts: list[PriceForecast] = Field(default_factory=list,max_length=9)
    generated_at: str
    model: str
    status: Literal['ready','partial','insufficient','stale']
    rejected: int = 0
    limitations: list[str] = Field(default_factory=list)
