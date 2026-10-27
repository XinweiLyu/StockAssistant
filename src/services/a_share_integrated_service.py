"""Durable evidence preparation and immutable integrated research snapshots."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import wraps
import threading

from src.services.a_share_research_progress import progress_view
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_integrated import ResearchBundle, VERSION, digest, stamp, canonical_plan_day, earnings_stage
from src.services.a_share_market_jobs import MarketJobs
from src.services.a_share_market_service import configuration_stamp, source_signature, price_family
from src.services.a_share_outlook_service import merged_bars
from src.services.a_share_event_cases import event_context, extract_event_facts, match_event_cases, case_price_references, effective_event_families
from data_provider.a_share_fundamentals import ResearchSources, financial_coverage
from data_provider.a_share_disclosures import fetch_disclosure_text
from src.services.a_share_disclosure_batch import prepare_disclosure_batch
from src.services.a_share_event_lifecycle import annotate_lifecycles


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

    def _eligibility(self, stock):
        return dict(identity_verified=stock.get('identity_verified'), st=stock.get('st'), board=stock.get('board'),
                    major_risk=bool(self.assistant.major_risks().get(stock['code'], False)))

    def _expired_plans(self, report):
        today = date.fromisoformat(self._now()[:10])
        for plan in report.get('plans', []):
            try:
                if date.fromisoformat(canonical_plan_day(plan.get('valid_until'))) < today:
                    return True
            except (ValueError, TypeError, AttributeError):
                return True
        return False

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
        stock = self.assistant.market.stock(code)
        repo, key = self.assistant.repo, self.key(code)
        pointer = repo.latest(self.profile, 'research_pointer', key=key, default={})
        bundle = self.bundle(pointer['data_hash']) if pointer.get('data_hash') else None
        report = repo.latest(self.profile, 'integrated_report', key=key)
        task_pointer = self.assistant.market.repo.get_state(self.profile, 'research_task:' + code, {})
        task = self.assistant.market.repo.task(task_pointer.get('id')) if task_pointer.get('id') else None
        running = self._running.get(key)
        status = 'missing'
        stale_reasons = []
        if bundle:
            status = 'ready'
            if bundle.get('version') != VERSION:
                stale_reasons.append('研究规则版本已更新，请更新资料')
            if bundle['history_binding'] != self._binding(code):
                stale_reasons.append('完整历史或价格锚点已变化')
            if bundle['context'].get('source_signature') != list(source_signature(self.assistant.settings)):
                stale_reasons.append('数据来源配置已变化')
            if bundle['context'].get('eligibility_binding') is None:
                stale_reasons.append('旧版资料缺少证券资格与风险快照，请更新资料')
            elif bundle['context']['eligibility_binding'] != self._eligibility(stock):
                stale_reasons.append('证券资格或已核实重大风险已变化，旧策略仅供历史对照')
            if stale_reasons:
                status = 'stale'
        if task and task['state'] in ('pending', 'running'):
            status = 'preparing'
        elif task and task['state'] == 'failed' and not bundle:
            status = 'failed'
        if report:
            if self._expired_plans(report):
                stale_reasons.append('研究计划已过期或有效日期无效')
            if self.assistant.settings.model and report.get('model') != self.assistant.settings.model:
                stale_reasons.append('研究模型配置已变化')
            if not bundle or report['data_hash'] != bundle['data_hash'] or stale_reasons:
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
        return dict(code=code, status=status, bundle=bundle, report=report, stale_reasons=stale_reasons,
                    task={k:task[k] for k in ('id','state','error','updated_at')} if task else None,
                    progress=progress_view(running,self._now()), demo=self.profile == 'demo',
                    peer_progress=peer_progress,
                    validation=self.validation(code) if report else None,
                    message=waiting.get('reason') or '；'.join(stale_reasons) or '资料与预测按独立时间版本留存；读取不调用模型')

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

    def _case_library(self, target_code, events, cutoff, industry, elapsed_sessions=0, histories_cache=None):
        svc, market = self.assistant, self.assistant.market
        all_events = []
        peers = market.repo.members(self.profile, industry['sector_id']).get('codes', []) if industry else []
        for code in list(dict.fromkeys([target_code] + peers))[:501]:
            data = svc.repo.latest(self.profile, 'research_data', key=self.key(code), default={})
            selected = events if code == target_code else data.get('events', [])
            if not selected:
                continue
            snapshots = svc.repo.records(self.profile, 'industry_archive', key=self.key(code), limit=200)
            cache = histories_cache if histories_cache is not None else {}
            if code not in cache:
                cache[code] = self._histories(code, industry.get('sector_id') if industry else None)
            histories = cache[code]
            known_events = [e for e in selected if stamp(e.get('published_at')) and stamp(e['published_at']) <= cutoff]
            for event in effective_event_families(known_events):
                if not event.get('text'):
                    continue
                extracted = extract_event_facts(event, data.get('facts', []))
                when = extracted.get('published_at') or ''
                known = next((r['payload'] for r in snapshots if r['payload']['observed_at'] <= when), None)
                extracted.update(industry_id=(known or {}).get('sector_id') or (industry or {}).get('sector_id'),
                                 industry_quality='archived' if known else 'current_membership_only', valuation_percentile=None)
                observed = event_context(extracted, histories, market.calendar(), cutoff, elapsed_sessions)
                stage = earnings_stage(event.get('title', '')) if event.get('kind') == 'earnings' else 0
                stage_day = observed.get('stage_anchor_date')
                stage_end = stamp(stage_day + 'T15:00:00+08:00') if stage_day else None
                if stage and event.get('report_period') and stage_end:
                    # Retire a historical guidance only when a later statement was
                    # already public at this case's aligned stage, never as of today.
                    replacements = [other for other in known_events
                        if other.get('kind') == 'earnings'
                        and other.get('report_period') == event['report_period']
                        and earnings_stage(other.get('title', '')) > stage
                        and stamp(event['published_at']) <= stamp(other['published_at']) <= stage_end]
                    observed['stage_state'] = 'superseded' if replacements else 'outstanding'
                all_events.append(observed)
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
                selected_events.append(extracted)
        selected_events.sort(key=lambda e:e['published_at'], reverse=True)
        selected_events=effective_event_families(selected_events)
        selected_events=annotate_lifecycles(selected_events, days, context['anchor_date'])
        valuation = next((f for f in available if f['values'].get('pe_percentile') is not None),None)
        targets = [e for e in selected_events if e.get('active_catalyst')][:12]
        cohorts, cache = [], {}
        for event in targets:
            elapsed = event['age_sessions']
            library = self._case_library(code, selected_events, cutoff, industry, elapsed, cache)
            target = next((e for e in library if e['id'] == event['id'] and e['code'] == code), None)
            if target is None:
                continue
            target = target | dict(industry_id=(industry or {}).get('sector_id'),
                market_state=baseline.get('environment', {}).get('market_state', 'unknown'),
                valuation_percentile=valuation['values']['pe_percentile'] if valuation else None)
            cohort = match_event_cases(target, library, cutoff)
            cohort.update(target_event={k:v for k,v in target.items() if k not in ('text','outcomes')}, elapsed_sessions=elapsed)
            cohorts.append(cohort)
        # Retain compatibility for consumers of one primary cohort; never pool different mechanisms.
        cases = deepcopy(cohorts[0]) if cohorts else match_event_cases({}, [], cutoff)
        cases.setdefault('target_event', None)
        cases.setdefault('elapsed_sessions', 0)
        references = []
        for index, cohort in enumerate(cohorts):
            cohort['price_references'] = case_price_references(cohort, context['reference_price'])
            for ref in cohort['price_references']:
                ref['id'] += '_' + digest(cohort['target_event']['id'])[:10] if index else ''
                ref.update(target_event_id=cohort['target_event']['id'], elapsed_sessions=cohort['elapsed_sessions'])
            references.extend(cohort['price_references'])
        cases.update(cohorts=cohorts, price_references=references, diagnostics=dict(
            announcements=len(events or []), verified_texts=sum(e.get('text_status')=='ready' and bool(e.get('text')) for e in events or []),
            tracking_events=sum(bool(e.get('tracking_active')) for e in selected_events),
            quantified_targets=len(cohorts), omitted_targets=max(0,sum(bool(e.get('active_catalyst')) for e in selected_events)-len(cohorts)),
            unquantified_tracking=sum(bool(e.get('tracking_active')) and not e.get('active_catalyst') for e in selected_events)))
        if not cohorts:
            missing.append(cases['message'])
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
        eligibility = self._eligibility(stock)
        research_context = dict(price=context, industry=industry,financial_coverage=financial_coverage(available),
            **eligibility,eligibility_binding=eligibility,
            source_signature=list(source_signature(svc.settings)))
        # Source observations are frozen once. A refresh of identical content does not buy new inference.
        identity = digest(dict(version=VERSION, code=code, binding=binding,
            source_signature=source_signature(svc.settings), facts=[f.get('content_hash') or digest(f) for f in available],
            events=[{k:v for k,v in e.items() if k not in ('observed_at','available_at','text_attempted_at','text_attempts')} for e in selected_events],
            baseline=baseline['data_hash'], cases=cases,context=research_context,coverage=(coverage or [])+price_coverage,missing=missing))
        existing = self.bundle(identity)
        if existing:
            market.repo.set_state(self.profile, 'research_waiting:' + code, {})
            return existing
        bundle = ResearchBundle(code=code, name=stock['name'], cutoff=cutoff, anchor_date=context['anchor_date'],
            reference_price=context['reference_price'], source=context['source'], history_binding=binding,
            data_hash=identity, facts=available,
            events=list({e['id']:e for e in targets+[e for e in selected_events if e.get('tracking_active')][:24]+selected_events[:24]+[e for e in selected_events if e.get('text_status')=='ready'][:12]}.values()), cases=cases,
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
        previous = svc.repo.latest(self.profile, 'research_data', key=self.key(code), default={})
        if previous.get('source_signature') != list(source_signature(settings)):
            previous = {}
        events, text_coverage = prepare_disclosure_batch(disclosure['events'], previous.get('events', []),
            now, market.calendar(), end, fetch_disclosure_text)
        stock = market.stock(code)
        news = source.news(code, stock['name'], stock.get('industries', []), now) if payload.get('include_peers') else dict(status='missing', facts=[])
        facts = financial['facts'] + valuation['facts'] + news['facts']
        old_facts = {f['fact_id']:f for f in previous.get('facts', [])}
        facts = [old_facts.get(f['fact_id'], f) for f in facts]
        coverage = [dict(category='financial', status=financial['status'], count=len(financial['facts']), sources=sorted({f['source'] for f in financial['facts']}), errors=financial.get('errors', [])),
            dict(category='valuation', status=valuation['status'], count=len(valuation['history']), sources=sorted({f['source'] for f in valuation['facts']})),
            dict(category='disclosures', status=disclosure['status'], count=len(events), **text_coverage,
                 source='cninfo', errors=disclosure.get('errors', [])),
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
