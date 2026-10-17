"""Durable evidence preparation and immutable integrated research snapshots."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import wraps
import threading

from src.services.a_share_research_progress import progress_view
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_integrated import ResearchBundle, VERSION, digest, stamp
from src.services.a_share_market_jobs import MarketJobs
from src.services.a_share_market_service import configuration_stamp, source_signature, price_family
from src.services.a_share_outlook_service import merged_bars
from src.services.a_share_event_cases import event_context, extract_event_facts, match_event_cases, case_price_references, effective_event_families
from data_provider.a_share_fundamentals import ResearchSources, financial_coverage
from data_provider.a_share_disclosures import fetch_disclosure_text


class EvidenceNotReady(ValueError):
    """Only unavailable price history is a retryable evidence dependency."""


def settings_locked(method):
    @wraps(method)
    def run(self,*args,**kwargs):
        with self.assistant._settings_lock:
            return method(self,*args,**kwargs)
    return run


class IntegratedResearchService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.jobs = MarketJobs(assistant.market.repo, self.handle_task, profile=assistant.settings.mode, kinds=['research_data'])
        self._lock = threading.RLock()
        self._running = {}

    @property
    def profile(self):
        return self.assistant.settings.mode

    def key(self, code):
        return self.profile + ':' + code

    def _now(self):
        return stamp(self.assistant.market.clock().isoformat())

    def _binding(self, code):
        market = self.assistant.market
        end = market.completed_day()
        raw = market.repo.get_history(self.profile, 'stock:' + code, 'raw', '1900-01-01', end)
        qfq = market.repo.get_history(self.profile, 'stock:' + code, 'qfq', '1900-01-01', end)
        if not raw or not qfq or not raw['items'] or not qfq['items'] or price_family(raw['source']) != price_family(qfq['source']):
            return None
        if raw['items'][-1]['date'] != end or qfq['items'][-1]['date'] != end:
            return None
        return dict(anchor_date=end, source=raw['source'], raw_anchor=raw['items'][-1]['close'],
                    qfq_anchor=qfq['items'][-1]['close'], adjustment_basis=qfq['adjustment_basis'],
                    raw_fetched_at=raw['fetched_at'], qfq_fetched_at=qfq['fetched_at'])

    def bundle(self, data_hash):
        return self.assistant.repo.latest(self.profile, 'research_bundle', key=data_hash)

    def _industry(self, code):
        """Resolve hierarchical classifications only when verified memberships nest."""
        market = self.assistant.market
        groups = market.repo.associations(self.profile, [code]).get(code, [])
        groups = [g for g in groups if g['kind'] == 'industry' and g['classification'] == 'eastmoney-industry']
        candidates = [(g, set(market.repo.members(self.profile, g['sector_id'])['codes'])) for g in groups]
        candidates = [(g, members) for g, members in candidates if code in members]
        narrowest = [(g, members) for g, members in candidates
                     if all(members <= other for _, other in candidates)]
        # Equal or incomparable groups do not establish a unique child industry.
        return narrowest[0][0] if len(narrowest) == 1 else None

    @settings_locked
    def get(self, code):
        self.assistant.market.stock(code)
        repo, key = self.assistant.repo, self.key(code)
        pointer = repo.latest(self.profile, 'research_pointer', key=key, default={})
        bundle = self.bundle(pointer['data_hash']) if pointer.get('data_hash') else None
        report = repo.latest(self.profile, 'integrated_report', key=key)
        task_pointer = self.assistant.market.repo.get_state(self.profile, 'research_task:' + code, {})
        task = self.assistant.market.repo.task(task_pointer.get('id')) if task_pointer.get('id') else None
        running = self._running.get(key)
        status = 'missing'
        stale = False
        if bundle:
            status = 'ready'
            if (bundle.get('version') != VERSION or bundle['history_binding'] != self._binding(code) or
                    bundle['context'].get('source_signature') != list(source_signature(self.assistant.settings))):
                status = 'stale'
                stale = True
        if task and task['state'] in ('pending', 'running'):
            status = 'preparing'
        elif task and task['state'] == 'failed' and not bundle:
            status = 'failed'
        if report and (not bundle or report['data_hash'] != bundle['data_hash'] or stale or
                       (self.assistant.settings.model and report.get('model') != self.assistant.settings.model) or
                       any(p.get('valid_until','9999') < self._now()[:10] for p in report.get('plans',[]))):
            report = report | dict(stale=True)
        if running:
            status = 'running'
        waiting = self.assistant.market.repo.get_state(self.profile, 'research_waiting:' + code, {})
        if waiting and status not in ('running', 'preparing'):
            status = 'waiting_history'
        peer_state=self.assistant.market.repo.get_state(self.profile,'research_peers:'+code,{})
        peer_progress=dict(total=0,complete=0,pending=0,running=0,failed=0,next_offset=peer_state.get('next_offset',20))
        for identity in peer_state.get('task_ids',[]):
            child=self.assistant.market.repo.task(identity)
            if child and child['state'] in peer_progress:
                peer_progress['total']+=1
                peer_progress[child['state']]+=1
        if not running and task and task['state'] in ('pending','running'):
            running=dict(completed=0,expected=6,phase='preparing',current='资料准备',message='正在排队或获取财务、公告及新闻资料',started_at=task.get('created_at'))
        return dict(code=code, status=status, bundle=bundle, report=report,
                    task={k:task[k] for k in ('id','state','error','updated_at')} if task else None,
                    progress=progress_view(running,self._now()), demo=self.profile == 'demo',
                    peer_progress=peer_progress,
                    validation=self.validation(code) if report else None,
                    message=waiting.get('reason') or '资料与预测按独立时间版本留存；读取不调用模型')

    @settings_locked
    def prepare(self, code, peer_offset=0):
        stock = self.assistant.market.stock(code)
        if isinstance(peer_offset, bool) or not isinstance(peer_offset, int) or not 0 <= peer_offset <= 500:
            raise ValueError('同业批次起点须为0至500')
        if self.profile == 'demo':
            return dict(accepted=False, status='missing', demo=True, message='演示模式不抓取真实公司资料')
        settings = self.assistant.settings.model_copy(deep=True)
        day = self._now()[:10]
        signature = configuration_stamp(settings)
        previous = self.assistant.market.repo.get_state(self.profile, 'research_task:' + code, {})
        pending = self.assistant.market.repo.task(previous.get('id')) if previous.get('id') else None
        if (pending and pending['state'] in ('pending','running') and
                pending['payload'].get('peer_offset') == peer_offset and
                configuration_stamp(AssistantSettings.model_validate(pending['payload']['settings'])) == signature):
            return dict(accepted=True, status='preparing', task_id=pending['id'], code=code, demo=False,
                        message='相同研究资料任务已在后台执行')
        nonce = datetime.now(timezone.utc).isoformat()
        identity = self.jobs.submit(self.profile, 'research-data:' + code + ':' + day + ':' + str(peer_offset) + ':' + signature + ':' + nonce,
            'research_data', dict(code=code, root_code=code, peer_offset=peer_offset, settings=settings.model_dump(), include_peers=True), 35)
        self.assistant.market.repo.set_state(self.profile, 'research_task:' + code, {'id':identity})
        return dict(accepted=True, status='preparing', task_id=identity, code=code, demo=False,
                    message='后台准备财报、公告原文与新闻；本步骤不调用AI模型')

    def _histories(self, code, industry_id=None):
        market = self.assistant.market
        end = market.completed_day()
        raw = market.repo.get_history(self.profile, 'stock:' + code, 'raw', '1900-01-01', end)
        qfq = market.repo.get_history(self.profile, 'stock:' + code, 'qfq', '1900-01-01', end)
        stock = merged_bars(raw, qfq) if raw and qfq and price_family(raw['source']) == price_family(qfq['source']) else []
        output = dict(stock=stock)
        for kind, entity in [('benchmark', 'benchmark:000300'), ('industry', industry_id)]:
            history = market.repo.get_history(self.profile, entity, 'raw', '1900-01-01', end) if entity else None
            output[kind] = [dict(b, adjusted_close=b['close']) for b in (history or {}).get('items', [])]
        return output

    def _case_library(self, target_code, events, cutoff, industry, elapsed_sessions=0):
        svc, market = self.assistant, self.assistant.market
        all_events = []
        peers = market.repo.members(self.profile, industry['sector_id']).get('codes', []) if industry else []
        for code in list(dict.fromkeys([target_code] + peers))[:501]:
            data = svc.repo.latest(self.profile, 'research_data', key=self.key(code), default={})
            selected = events if code == target_code else data.get('events', [])
            if not selected:
                continue
            snapshots = svc.repo.records(self.profile, 'industry_archive', key=self.key(code), limit=200)
            histories = self._histories(code, industry.get('sector_id') if industry else None)
            for event in selected:
                if not event.get('text'):
                    continue
                extracted = extract_event_facts(event, data.get('facts', []))
                when = extracted.get('published_at') or ''
                known = next((r['payload'] for r in snapshots if r['payload']['observed_at'] <= when), None)
                extracted.update(industry_id=(known or {}).get('sector_id') or (industry or {}).get('sector_id'),
                                 industry_quality='archived' if known else 'current_membership_only', valuation_percentile=None)
                all_events.append(event_context(extracted, histories, market.calendar(), cutoff, elapsed_sessions))
        return all_events

    @settings_locked
    def freeze(self, code, facts, events=None, coverage=None):
        svc, market = self.assistant, self.assistant.market
        stock = market.stock(code)
        context, binding = svc.price_context(code), self._binding(code)
        if not context or not binding:
            raise EvidenceNotReady('需先补齐120个完整交易日及同源原始/复权资料')
        cutoff = self._now()
        available, missing = [], []
        for fact in facts:
            if fact.get('code') != code:
                raise ValueError('研究资料股票身份不一致')
            if stamp(fact.get('available_at')) and stamp(fact['available_at']) <= cutoff:
                available.append(fact)
            else:
                missing.append('未来或未知可用时间的资料已排除')
        industry = self._industry(code)
        baseline = svc.quant_outlook(code)
        days = market.calendar()
        selected_events = []
        for event in events or []:
            when = stamp(event.get('published_at'))
            if when and when <= cutoff:
                extracted = extract_event_facts(event, available)
                age = sum(when[:10] < d <= context['anchor_date'] for d in days)
                selected_events.append(extracted | dict(active_catalyst=age <= 20, age_sessions=age))
        selected_events.sort(key=lambda e:e['published_at'], reverse=True)
        selected_events=effective_event_families(selected_events)
        latest = next((e for e in selected_events if e.get('active_catalyst') and e.get('public_verified')), None)
        elapsed = latest['age_sessions'] if latest else 0
        library = self._case_library(code, selected_events, cutoff, industry, elapsed)
        current = max((e for e in library if e['code'] == code and e.get('active_catalyst')),
                      key=lambda e:e.get('published_at') or '', default={})
        target = current | dict(industry_id=(industry or {}).get('sector_id'),
            market_state=baseline.get('environment', {}).get('market_state', 'unknown'))
        valuation = next((f for f in available if f['values'].get('pe_percentile') is not None),None)
        target['valuation_percentile'] = valuation['values']['pe_percentile'] if valuation else None
        cases = match_event_cases(target, library, cutoff) if current else match_event_cases({}, library, cutoff)
        cases['target_event'] = {k:v for k,v in target.items() if k not in ('text','outcomes')} if current else None
        cases['elapsed_sessions'] = elapsed
        cases['price_references'] = case_price_references(cases, context['reference_price'])
        if not current:
            missing.append('近20个交易日暂无可核对原文的当前事件；旧消息不作为新增催化，历史案例不能生成数值影响')
        if not industry:
            missing.append('行业资料未核实或存在歧义')
        if not available:
            missing.append('财务和新闻资料尚未取得')
        missing.extend(['筹码未取得可核对的日期、来源和价格口径记录，未进入综合判断',
                        '逐笔资金流、机构持仓及一致预期未取得；成交额仅作流动性证据'])
        price_coverage = [dict(category='technical',status='ready',count=120,source=context['source']),
            dict(category='industry',status='ready' if industry else 'missing',count=1 if industry else 0,
                 source=(industry or {}).get('classification')),
            dict(category='liquidity',status='ready' if context['features'].get('avg_amount') else 'missing',count=20,
                 source=context['source']),dict(category='chips',status='missing',count=0)]
        research_context = dict(price=context, industry=industry,financial_coverage=financial_coverage(available),
            identity_verified=stock.get('identity_verified'),st=stock.get('st'),board=stock.get('board'),
            source_signature=list(source_signature(svc.settings)))
        # Source observations are frozen once. A refresh of identical content does not buy new inference.
        identity = digest(dict(version=VERSION, code=code, binding=binding,
            source_signature=source_signature(svc.settings), facts=[f.get('content_hash') or digest(f) for f in available],
            events=[{k:v for k,v in e.items() if k not in ('observed_at','available_at')} for e in selected_events],
            baseline=baseline['data_hash'], cases=cases,context=research_context,coverage=(coverage or [])+price_coverage,missing=missing))
        existing = self.bundle(identity)
        if existing:
            market.repo.set_state(self.profile, 'research_waiting:' + code, {})
            return existing
        bundle = ResearchBundle(code=code, name=stock['name'], cutoff=cutoff, anchor_date=context['anchor_date'],
            reference_price=context['reference_price'], source=context['source'], history_binding=binding,
            data_hash=identity, facts=available,
            events=list({e['id']:e for e in selected_events[:24]+[e for e in selected_events if e.get('text_status')=='ready'][:12]}.values()), cases=cases,
            baseline=baseline, context=research_context,
            coverage=(coverage or []) + price_coverage, missing=list(dict.fromkeys(missing)), demo=self.profile == 'demo').model_dump()
        svc.repo.append(self.profile, 'research_bundle', identity, bundle)
        svc.repo.append(self.profile, 'research_pointer', self.key(code), dict(data_hash=identity, cutoff=cutoff))
        market.repo.set_state(self.profile, 'research_waiting:' + code, {})
        return bundle

    def handle_task(self, task):
        svc, market = self.assistant, self.assistant.market
        payload = task['payload']
        settings = AssistantSettings.model_validate(payload['settings'])
        if task['profile'] != self.profile or source_signature(settings) != source_signature(svc.settings):
            return
        if self.profile == 'demo':
            return
        code, now = payload['code'], self._now()
        end = market.completed_day()
        start = (date.fromisoformat(end)-timedelta(days=1825)).isoformat()
        for adjust in ('raw','qfq'):
            market.history(code, start, end, adjust)
        source = ResearchSources(svc._provider(), settings)
        financial = source.financials(code, now)
        valuation = source.valuation(code, now)
        disclosure = source.disclosures(code, start, now[:10], now)
        events = disclosure['events']
        priorities = sorted(events, key=lambda e: (0 if '业绩预告' in e['title'] else 1 if '快报' in e['title'] else 2 if e['kind']=='regulatory' else 3, -int(e['published_at'][:10].replace('-',''))))
        previous = svc.repo.latest(self.profile, 'research_data', key=self.key(code), default={})
        if previous.get('source_signature') != list(source_signature(settings)):
            previous = {}
        old_events = {e['id']:e for e in previous.get('events', [])}
        for event in priorities[:6]:
            old = old_events.get(event['id'])
            if old and old.get('text_status') == 'ready':
                event.update({k:old[k] for k in ('text','text_status','text_hash')})
                continue
            document = fetch_disclosure_text(event['url'], event['published_at'][:10])
            event.update(text=document.get('text', ''), text_status=document['status'], text_hash=document.get('content_hash'))
        stock = market.stock(code)
        news = source.news(code, stock['name'], stock.get('industries', []), now) if payload.get('include_peers') else dict(status='missing', facts=[])
        facts = financial['facts'] + valuation['facts'] + news['facts']
        old_facts = {f['fact_id']:f for f in previous.get('facts', [])}
        facts = [old_facts.get(f['fact_id'], f) for f in facts]
        coverage = [dict(category='financial', status=financial['status'], count=len(financial['facts']), sources=sorted({f['source'] for f in financial['facts']}), errors=financial.get('errors', [])),
            dict(category='valuation', status=valuation['status'], count=len(valuation['history']), sources=sorted({f['source'] for f in valuation['facts']})),
            dict(category='disclosures', status=disclosure['status'], count=len(events), texts=sum(e.get('text_status')=='ready' for e in events), source='cninfo', errors=disclosure.get('errors', [])),
            dict(category='news', status=news['status'], count=len(news['facts']), limitations=news.get('limitations', []))]
        with market._publication(task):
            if task['profile'] != self.profile or source_signature(settings) != source_signature(svc.settings):
                return
            svc.repo.append(self.profile, 'research_data', self.key(code), dict(facts=facts, events=events, coverage=coverage,
                source_signature=list(source_signature(settings)),valuation_history=valuation['history'],fetched_at=now))
            industry = self._industry(code)
            if industry:
                svc.repo.append(self.profile, 'industry_archive', self.key(code), dict(sector_id=industry['sector_id'], observed_at=now))
            try:
                self.freeze(code, facts, events, coverage)
            except EvidenceNotReady:
                # Data survives while price jobs catch up; GET does not perform that work.
                market.repo.set_state(self.profile, 'research_waiting:' + code, dict(reason='等待完整同源历史', fetched_at=now))
        if payload.get('include_peers') and industry:
            peers = market.repo.members(self.profile, industry['sector_id']).get('codes', [])
            peers = [c for c in peers if c != code][payload.get('peer_offset', 0):payload.get('peer_offset', 0)+20]
            identities=[]
            for peer in peers:
                identity = self.jobs.submit(self.profile, f'research-peer:{peer}:{now[:10]}:{configuration_stamp(settings)}',
                    'research_data', dict(code=peer, root_code=code, settings=settings.model_dump(), include_peers=False), 95)
                identities.append(identity)
            with market._publication(task):
                state=market.repo.get_state(self.profile,'research_peers:'+code,{})
                market.repo.set_state(self.profile,'research_peers:'+code,dict(
                    task_ids=list(dict.fromkeys(state.get('task_ids',[])+identities))[-520:],
                    next_offset=min(520,payload.get('peer_offset',0)+20)))
        # Root generation will freeze again from saved data after all requested evidence is ready.

    @settings_locked
    def generate(self, code, force=False):
        stock = self.assistant.market.stock(code)
        data = self.assistant.repo.latest(self.profile, 'research_data', key=self.key(code), default={})
        if data:
            if data.get('source_signature') != list(source_signature(self.assistant.settings)):
                return dict(accepted=False,status='stale',message='研究资料来自旧配置或缺少来源签名，请先更新研究资料；尚未调用模型')
            try:
                self.freeze(code, data['facts'], data['events'], data['coverage'])
            except EvidenceNotReady:
                return dict(accepted=False, status='preparing', message='完整历史尚未就绪，请先更新研究资料和行情')
        state = self.get(code)
        if not state['bundle'] or state['status'] in ('preparing', 'stale', 'waiting_history'):
            return dict(accepted=False, status=state['status'], message='请先更新研究资料；尚未调用模型')
        settings = self.assistant.settings.model_copy(deep=True)
        if not settings.research_enabled:
            return dict(accepted=False, status='disabled', message='请先启用增强研究并配置模型')
        bundle = deepcopy(state['bundle'])
        key = self.key(code)
        with self._lock:
            if key in self._running:
                return dict(accepted=False, status='running', message='该股票综合研究正在运行')
            if state.get('report') and not state['report'].get('stale') and state['report'].get('status') == 'complete' and state['report']['data_hash'] == bundle['data_hash'] and not force:
                return dict(accepted=False, status='ready', cached=True, message='已有相同资料的综合研究，可直接查看')
            self._running[key] = dict(completed=0, expected=6, phase='research',started_at=self._now(),message='正在准备专家输入')
        def run():
            try:
                from src.services.a_share_research import ResearchEngine
                result = ResearchEngine(self.assistant.repo).run_integrated(bundle, settings, self._now()[:10], manual=True,
                    progress=lambda p:self._running.update({key:p}),force=force)
                with self.assistant._settings_lock:
                    if self.profile == settings.mode and source_signature(settings) == source_signature(self.assistant.settings):
                        self.assistant.repo.append(settings.mode, 'integrated_report', key, result)
            except Exception as exc:
                self.assistant.repo.append(settings.mode, 'integrated_report', key,
                    dict(code=code, data_hash=bundle['data_hash'], status='failed', roles=[], forecasts=[], plans=[],
                         generated_at=datetime.now(timezone.utc).isoformat(), error=type(exc).__name__))
            finally:
                with self._lock:
                    self._running.pop(key, None)
        threading.Thread(target=run, daemon=True, name='integrated-' + code).start()
        return dict(accepted=True, status='running', expected_calls=6,
                    message='综合研究已启动，手动调用不受每日次数限制；按实际用量计费')

    @settings_locked
    def validation(self, code):
        self.assistant.market.stock(code)
        from src.services.a_share_integrated_validation import evaluate_integrated_snapshots, compare_forecast_snapshots
        market=self.assistant.market
        cutoff=market.completed_day()
        raw=market.repo.get_history(self.profile,'stock:'+code,'raw','1900-01-01',cutoff)
        records=self.assistant.repo.records(self.profile,'integrated_report',key=self.key(code),limit=1000)
        args=(records,(raw or {}).get('items',[]),market.calendar(),cutoff)
        source=(raw or {}).get('source')
        return evaluate_integrated_snapshots(*args,source=source) | dict(code=code,
            comparison=compare_forecast_snapshots(*args,source=source))
