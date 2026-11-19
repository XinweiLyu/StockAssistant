"""Market context adapters around the existing six-expert research pipeline."""
from datetime import date,timedelta
from src.services.a_share_integrated_service import IntegratedResearchService,EvidenceNotReady
from src.services.a_share_market_service import source_signature
from src.services.a_share_outlook_service import merged_bars
from src.schemas.a_share_integrated import digest
from src.services.a_share_outlook_service import OutlookService


class WorkspaceOutlookService(OutlookService):
    def _events(self,code,now):
        data=self.assistant.repo.latest(self.assistant.settings.mode,'research_data',key=self.assistant.settings.mode+':'+code,default={})
        return [e|dict(verified=False,first_seen=e.get('observed_at')) for e in data.get('events',[])],False


class WorkspaceResearchService(IntegratedResearchService):
    def __init__(self,assistant,sources):super().__init__(assistant);self.sources=sources

    def _industry(self,code):
        groups=self.assistant.market.repo.associations(self.profile,[code]).get(code,[])
        rows=[s for s in groups if s['kind']=='industry' and s['classification']=='yahoo-industry']
        return rows[0] if len(rows)==1 else None

    def _histories(self,code,industry_id=None):
        market=self.assistant.market;end=market.completed_day()
        raw=market.repo.get_history(self.profile,'stock:'+code,'raw','1900-01-01',end)
        adj=market.repo.get_history(self.profile,'stock:'+code,'qfq','1900-01-01',end)
        bm=market.repo.get_history(self.profile,'benchmark:'+market.market_name,'raw','1900-01-01',end)
        return dict(stock=merged_bars(raw,adj) if raw and adj and raw['adjustment_basis']==adj['adjustment_basis'] else [],
            benchmark=[b|dict(adjusted_close=b['close']) for b in (bm or {}).get('items',[])],industry=[])

    def _eligibility(self,stock):
        return dict(identity_verified=stock.get('identity_verified'),st=None,board=stock.get('board'),
            asset_type=stock.get('asset_type'),major_risk=False,market=self.assistant.market.market_name)

    def _binding(self,code):
        binding=super()._binding(code)
        if not binding:return None
        market=self.assistant.market;end=market.completed_day()
        raw=market.repo.get_history(self.profile,'stock:'+code,'raw','1900-01-01',end)
        adjusted=market.repo.get_history(self.profile,'stock:'+code,'qfq','1900-01-01',end)
        return binding if raw and adjusted and raw['adjustment_basis']==adjusted['adjustment_basis'] else None

    def handle_task(self,task):
        market=self.assistant.market;task=market._captured_task(task)
        with market._publication(task):pass
        code=task['payload']['code'];identity=market.identity(code)
        if list(source_signature(self.assistant.settings))!=list(source_signature(type(self.assistant.settings).model_validate(task['payload']['settings']))):return
        market.stock(code)
        market.handle_task(task|dict(kind='workspace_identity'))
        metadata=market.repo.get_state(self.profile,'identity:'+code,{})
        data=self.sources.fetch(identity,metadata,self._now())
        data.update(code=code,fetched_at=self._now(),source_signature=list(source_signature(self.assistant.settings)))
        with market._publication(task):
            self.assistant.repo.append(self.profile,'research_data',self.key(code),data)
        if not task['payload'].get('value_only'):
            end=market.completed_day();day=date.fromisoformat(end)
            try:start=day.replace(year=day.year-5).isoformat()
            except ValueError:start=day.replace(year=day.year-5,day=28).isoformat()
            market.handle_task(task|dict(kind='workspace_history',payload=task['payload']|dict(start=start,end=end)))
            try:
                symbol='^GSPC' if identity.market=='us' else '^HSI'
                benchmark=market.provider.history(identity.model_copy(update={'source_symbol':symbol}),start,end)
                with market._publication(task):
                    market.repo.replace_history(self.profile,'benchmark:'+identity.market,'raw',benchmark['source'],benchmark['basis'],benchmark['raw'],benchmark['fetched_at'],start,end)
            except Exception as exc:
                data['coverage'].append(dict(category='benchmark',status='failed',count=0,error=type(exc).__name__))
            try:
                with market._publication(task):self.freeze(code,data['facts'],data.get('events',[]),data['coverage'])
            except EvidenceNotReady:
                with market._publication(task):
                    market.repo.set_state(self.profile,'research_waiting:'+code,dict(reason='完整日线或复权配对不足，尚未形成综合预测资料'))
        with market._publication(task):self.assistant.value.capture(code)

    def freeze(self,code,facts,events=None,coverage=None):
        result=super().freeze(code,facts,events,coverage)
        market=self.assistant.market;stock=market.stock(code)
        context=result['context'];context.update(market=market.market_name,currency=stock.get('currency'),
            timezone=stock.get('timezone'),benchmark='^GSPC' if market.market_name=='us' else '^HSI')
        # Currency and market are part of content identity, not presentation-only metadata.
        identity=digest(result|dict(context=context,data_hash=None))
        result=result|dict(context=context,data_hash=identity)
        self.assistant.repo.append(self.profile,'research_bundle',identity,result)
        self.assistant.repo.append(self.profile,'research_pointer',self.key(code),dict(data_hash=identity,cutoff=result['cutoff']))
        return result
