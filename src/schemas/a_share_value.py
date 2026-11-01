"""Current-vintage value research; separate from short-term price forecasts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, field_validator, model_validator

VERSION = 'value-research-v4'


class ValueModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ValueFact(ValueModel):
    fact_id: str
    code: str = Field(pattern=r'^\d{6}$')
    metric: str
    value: StrictFloat
    unit: Literal['CNY', 'shares', 'ratio', 'CNY/share', 'multiple']
    currency: Literal['CNY'] = 'CNY'
    report_period: str
    period_start: str | None = None
    period_end: str
    period_basis: Literal['instant', 'ytd', 'quarter', 'annual']
    scope: Literal['consolidated', 'parent', 'unknown']
    attribution: Literal['all_claims', 'parent_common', 'minority', 'unknown']
    source: str
    raw_field: str
    published_at: str | None = None
    revised_at: str | None = None
    observed_at: str
    available_at: str
    vintage_quality: Literal['latest_reconstructed', 'user_attested'] = 'latest_reconstructed'
    content_hash: str
    url: str | None = None
    quote: str | None = None
    supersedes_fact_id: str | None = None
    conflicts: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def capital_contract(self):
        validate_current_capital(self)
        if self.metric == 'current_shares':
            from src.schemas.a_share_integrated import stamp
            period, observed, available = stamp(self.period_end), stamp(self.observed_at), stamp(self.available_at)
            if not period or not observed or not available or period[:10] != self.report_period or period[:10] > observed[:10] or observed > available:
                raise ValueError('当前股本的核对日、观察和可用日期不一致')
        return self


def validate_current_capital(fact):
    if fact.metric == 'current_shares' and (fact.unit != 'shares' or fact.period_basis != 'instant'
            or fact.scope != 'consolidated' or fact.attribution != 'parent_common' or fact.value <= 0):
        raise ValueError('当前总股本须为正数普通股股数、股单位、合并主体和时点口径')


class HoldingCase(ValueModel):
    months: Literal[6, 12, 24, 36]
    method: Literal['fcff', 'fcfe', 'rim', 'ddm', 'nav'] | None = None
    scenario: Literal['conservative', 'base', 'upside'] = 'base'
    realization_factor: StrictFloat | None = Field(default=None, ge=0, le=5)
    costs_per_share: StrictFloat | None = Field(default=None, ge=0)


class MonitorRule(ValueModel):
    id: str = Field(min_length=1,max_length=80)
    metric: Literal['revenue','net_profit','operating_cashflow','capex','roe','operating_margin','cash_conversion','roic_proxy','cash_surplus_proxy']
    operator: Literal['lt','lte','gt','gte']
    threshold: StrictFloat
    unit: Literal['CNY','ratio']
    basis: Literal['ttm'] = 'ttm'
    target_period: str | None = None
    review_on: str | None = None
    sources: list[str] = Field(min_length=1,max_length=30)
    rationale: str = Field(min_length=3,max_length=1000)

    @field_validator('target_period','review_on')
    @classmethod
    def dates(cls,value):
        if value is not None:
            from datetime import date
            if date.fromisoformat(value).isoformat()!=value:raise ValueError('日期须为YYYY-MM-DD')
        return value


class ForecastObservation(ValueModel):
    metric: Literal['revenue','net_profit','operating_cashflow','capex','roe','operating_margin','cash_conversion','roic_proxy','cash_surplus_proxy']
    period: str
    value: StrictFloat
    unit: Literal['CNY','ratio']
    basis: Literal['ttm'] = 'ttm'
    sources: list[str] = Field(min_length=1,max_length=30)
    rationale: str = Field(min_length=3,max_length=1000)
    origin: Literal['user_assumption','company_history','model_proposal'] = 'user_assumption'

    @field_validator('period')
    @classmethod
    def period_date(cls,value):
        from datetime import date
        if date.fromisoformat(value).isoformat()!=value:raise ValueError('日期须为YYYY-MM-DD')
        return value


class ValueSnapshot(ValueModel):
    version: str = VERSION
    snapshot_id: str
    code: str = Field(pattern=r'^\d{6}$')
    name: str
    cutoff: str
    facts: list[ValueFact] = Field(default_factory=list)
    financial_view: dict = Field(default_factory=dict)
    economic_model: dict = Field(default_factory=dict)
    peers: dict = Field(default_factory=dict)
    evidence: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    distributions: list[dict] = Field(default_factory=list)
    cases: list[dict] = Field(default_factory=list)
    binding: dict = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)


class ValueAssumptions(ValueModel):
    snapshot_id: str
    code: str = Field(pattern=r'^\d{6}$')
    revision: int = Field(default=0, ge=0)
    confirmed: bool = False
    primary_method: Literal['fcff', 'fcfe', 'rim', 'ddm', 'nav'] = 'fcff'
    cases: list[dict] = Field(default_factory=list, max_length=15)
    margin_required: StrictFloat | None = Field(default=None, ge=0, le=.8)
    peer_confirmations: list[dict] = Field(default_factory=list, max_length=100)
    driver_changes: list[dict] = Field(default_factory=list, max_length=30)
    holding_cases: list[HoldingCase] = Field(default_factory=list, max_length=12)
    theses: list[dict] = Field(default_factory=list, max_length=20)
    risk_review: dict = Field(default_factory=dict)
    economic_model_override: dict | None = None
    cycle_review: dict = Field(default_factory=dict)
    monitor_rules: list[MonitorRule] = Field(default_factory=list,max_length=30)
    forecast_observations: list[ForecastObservation] = Field(default_factory=list,max_length=30)

    @model_validator(mode='after')
    def unique_records(self):
        ids=[r.id for r in self.monitor_rules]
        forecasts=[(r.metric,r.period,r.basis) for r in self.forecast_observations]
        if len(ids)!=len(set(ids)) or len(forecasts)!=len(set(forecasts)):
            raise ValueError('复核规则ID或预测期间指标不能重复')
        return self

    @field_validator('cases', 'driver_changes', 'theses', 'risk_review', 'peer_confirmations', 'economic_model_override', 'cycle_review')
    @classmethod
    def bounded_json(cls, value):
        import json
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 100_000:
            raise ValueError('研究输入超过100KB')
        return value


class ValueReport(ValueModel):
    code: str
    snapshot_id: str
    assumptions_revision: int
    version: str = VERSION
    valuation_state: str
    parameter_origin: Literal['reference_sensitivity_v1'] | None = None
    generated_at: str
    primary_method: str
    valuation_cases: list[dict] = Field(default_factory=list)
    comparison: dict = Field(default_factory=dict)
    quality: dict = Field(default_factory=dict)
    peers: dict = Field(default_factory=dict)
    theses: list[dict] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    holding_cases: list[dict] = Field(default_factory=list)
    driver_effects: list[dict] = Field(default_factory=list)
    sensitivities: list[dict] = Field(default_factory=list)
    stale_reasons: list[str] = Field(default_factory=list)


class PrepareValueRequest(ValueModel):
    peer_offset: int = Field(default=0, ge=0, le=500)
    refresh: bool = False


class GenerateValueRequest(ValueModel):
    snapshot_id: str
    force: bool = False


class SaveValueRequest(ValueModel):
    snapshot_id: str
    expected_revision: int = Field(ge=0)
    assumptions: ValueAssumptions
    confirmed: bool = False


class EvaluateValueRequest(ValueModel):
    snapshot_id: str
    assumptions_revision: int = Field(ge=1)


class SupplementFact(ValueModel):
    metric: str = Field(max_length=80)
    value: StrictFloat
    unit: Literal['CNY', 'shares', 'ratio', 'CNY/share', 'multiple']
    report_period: str
    period_basis: Literal['instant', 'ytd', 'quarter', 'annual']
    scope: Literal['consolidated', 'parent', 'unknown']
    attribution: Literal['all_claims', 'parent_common', 'minority', 'unknown']
    url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    published_at: str
    quote: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)
    supersedes_fact_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode='after')
    def capital_contract(self):
        validate_current_capital(self)
        return self

    @field_validator('url')
    @classmethod
    def public_url(cls, value):
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
            raise ValueError('来源须为HTTP/HTTPS原文链接')
        return value


class SupplementValueRequest(ValueModel):
    snapshot_id: str
    facts: list[SupplementFact] = Field(min_length=1, max_length=50)
    attested: Literal[True]
