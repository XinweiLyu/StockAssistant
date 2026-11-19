"""Source-defined sector flows; snapshots are observations, never additive trades."""
from datetime import date,datetime,timezone
from typing import Literal
from zoneinfo import ZoneInfo
import re
from pydantic import BaseModel,ConfigDict,Field,model_validator
def utc_time(value):
    when=datetime.fromisoformat(value.replace('Z','+00:00'))
    if when.tzinfo is None:raise ValueError('时间须包含时区')
    return when.astimezone(timezone.utc).isoformat()

CATEGORIES=('main','super','large','medium','small')


class FlowPoint(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    sector_id:str
    kind:Literal['industry','concept']
    classification:str
    name:str
    source:str='eastmoney/sector-flow'
    measure:Literal['daily_net','cumulative_snapshot']
    unit:Literal['CNY']='CNY'
    observed_at:str
    session_day:str
    source_date:str|None=None
    source_time:str|None=None
    values:dict[str,float|None]
    ratios:dict[str,float|None]=Field(default_factory=dict)
    change:float|None=None
    close:float|None=Field(None,gt=0)
    date_quality:Literal['source_date','query_context']='query_context'
    vintage_quality:Literal['latest_reconstructed']='latest_reconstructed'

    @model_validator(mode='after')
    def identity_and_times(self):
        if not re.fullmatch('em:'+self.kind+r':BK\d{4}',self.sector_id) or self.classification!='eastmoney-'+self.kind:
            raise ValueError('板块代码或分类口径不一致')
        when=datetime.fromisoformat(self.observed_at.replace('Z','+00:00'))
        if when.tzinfo is None:raise ValueError('观察时间须包含时区')
        local_day=when.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
        date.fromisoformat(self.session_day)
        if self.source_date:
            date.fromisoformat(self.source_date)
            if self.source_date>local_day:raise ValueError('源日期不能在观察日之后')
        if self.measure=='daily_net' and (self.source_date is None or self.session_day!=self.source_date):
            raise ValueError('日净额须具有真实源日期')
        if self.measure=='cumulative_snapshot' and self.session_day!=local_day:
            raise ValueError('采样曲线按系统观测日隔离')
        if set(self.values)!=set(CATEGORIES) or set(self.ratios)-set(CATEGORIES):raise ValueError('资金类别无效')
        self.observed_at=utc_time(self.observed_at)
        if self.source_time:self.source_time=utc_time(self.source_time)
        return self
