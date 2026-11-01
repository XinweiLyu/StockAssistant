"""Immutable value snapshots, optimistic assumptions and explicit user actions."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from sqlalchemy import select
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_integrated import digest, stamp
from src.schemas.a_share_value import VERSION, ValueFact, ValueSnapshot, ValueAssumptions
from src.services.a_share_integrated_service import settings_locked
from src.services.a_share_market_service import configuration_stamp, source_signature
from src.services.a_share_market_jobs import MarketJobs
from src.services.a_share_value_financials import build_financial_view
from src.services.a_share_value_peers import select_economic_model, build_peer_comparison
from src.services.a_share_value_valuation import evaluate_value, compare_price
from src.services.a_share_value_drivers import apply_driver_changes
from src.services.a_share_value_holding import evaluate_holding
from src.repositories.a_share_repository import JOURNAL, utc_now


class ValueConflict(ValueError):
    """A stale snapshot or competing editor; expose as HTTP 409."""


class ValueResearchService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.jobs = MarketJobs(assistant.market.repo, self.handle_task, profile=assistant.settings.mode, kinds=['value_research'])

    @property
    def profile(self):
        return self.assistant.settings.mode

    def key(self, code):
        return self.profile+':'+code

    def now(self):
        return stamp(self.assistant.market.clock().isoformat())

    def _stock(self, code):
        # Do not call demo bootstrap from a read-only value endpoint.
        if not self.assistant.market.repo.stock(self.profile, code):
            raise ValueError('当前目录中没有该股票')
        return self.assistant.market.stock(code)

    def _data(self, code):
        return self.assistant.repo.latest(self.profile, 'research_data', key=self.key(code), default={})

    def _latest(self, kind, code):
        return self.assistant.repo.latest(self.profile, kind, key=self.key(code))

    def _quote(self, stock):
        quote = deepcopy(stock.get('quote') or {})
        today = self.now()[:10]
        valid_days = {self.assistant.market.completed_day(), today}
        quote['valid'] = (isinstance(quote.get('price'), (int, float)) and not isinstance(quote.get('price'), bool)
                          and quote.get('price', 0) > 0 and quote.get('trade_date') in valid_days and bool(quote.get('source_time')))
        quote['basis'] = 'raw'
        return quote

    def _eligibility(self, stock):
        major = bool(self.assistant.major_risks().get(stock['code']))
        return dict(identity_verified=bool(stock.get('identity_verified')), st=bool(stock.get('st')),
            major_risk=major, board=stock.get('board'),
            eligible=bool(stock.get('identity_verified')) and not stock.get('st') and not major and self.profile != 'demo')

    def _binding(self, stock, data):
        industry = self.assistant.integrated._industry(stock['code'])
        return dict(source_signature=list(source_signature(self.assistant.settings)),
            configuration=configuration_stamp(self.assistant.settings), eligibility=self._eligibility(stock),
            industry=industry, facts_hash=digest(data.get('value_facts', [])),
            historical_context_hash=digest([data.get('valuation_history', []),data.get('distributions', []),self._case_library(stock['code'],self.now())]),
            evidence_hash=digest([data.get('facts', []), data.get('events', [])]),
            disclosure_coverage_hash=digest([c for c in data.get('coverage',[]) if c.get('category')=='disclosures']))

    def _peer_row(self, stock, data, model, view, industry):
        # Membership in the target board is a candidate relation, never a
        # substitute for the other company's own verified economic identity.
        industry = self.assistant.integrated._industry(stock['code'])
        model = select_economic_model(industry, [], None)
        metrics, basis = {}, {}
        for f in sorted(data.get('facts', []), key=lambda f:f.get('values', {}).get('trade_date') or ''):
            for key, target in [('pe_ttm', 'pe'), ('pb', 'pb')]:
                day = f.get('values', {}).get('trade_date')
                if f.get('values', {}).get(key) is not None and day and day <= self.now()[:10]:
                    metrics[target] = f['values'][key]
                    basis[target] = dict(date=day, definition=key, source=f.get('source'), fact_ids=[f.get('fact_id')])
        latest = view.get('latest', {})
        equity = latest.get('parent_equity', {}).get('value')
        ttm = view.get('ttm', {})
        if equity and equity > 0 and ttm.get('net_profit'):
            metrics['roe'] = ttm['net_profit']['value']/equity
            basis['roe'] = dict(date=view.get('latest_period'),definition='parent_profit_TTM/end_parent_equity',
                source=ttm['net_profit']['vendor'],fact_ids=ttm['net_profit']['fact_ids']+latest['parent_equity']['fact_ids'])
        return dict(code=stock['code'], name=stock.get('name'), verified=bool(stock.get('identity_verified')),
            industry_id=(industry or {}).get('sector_id'), economic_model=model['model'],
            period=view.get('latest_period'), parent_equity=equity, metrics=metrics, metric_basis=basis)

    def _case_library(self, code, cutoff):
        from src.schemas.a_share_integrated import VERSION as INTEGRATED_VERSION
        pointer = self.assistant.repo.latest(self.profile, 'research_pointer', key=self.key(code), default={})
        bundle = self.assistant.integrated.bundle(pointer['data_hash']) if pointer.get('data_hash') else None
        if (not bundle or bundle.get('version') != INTEGRATED_VERSION or bundle.get('code') != code
            or not bundle.get('cutoff') or bundle['cutoff'] > cutoff
            or bundle.get('context', {}).get('source_signature') != list(source_signature(self.assistant.settings))
            or bundle.get('history_binding') != self.assistant.integrated._binding(code)):
            return []
        cases = bundle.get('cases')
        return [cases] if isinstance(cases, dict) and cases else cases if isinstance(cases, list) else []

    @settings_locked
    def capture(self, code):
        stock, data = self._stock(code), self._data(code)
        if not data or data.get('source_signature') != list(source_signature(self.assistant.settings)):
            raise ValueConflict('尚无当前来源的价值资料，请先补齐资料')
        facts = deepcopy(data.get('value_facts', []))
        supplements = self.assistant.repo.latest(self.profile, 'value_supplements', key=self.key(code), default=[])
        retired = {f.get('supersedes_fact_id') for f in supplements if f.get('supersedes_fact_id')}
        facts += [f for f in supplements if f['fact_id'] not in retired]
        cutoff = self.now()
        view = build_financial_view(facts, cutoff)
        from src.services.a_share_value_context import own_valuation_history
        view['valuation_history'] = own_valuation_history(data.get('valuation_history', []), cutoff, self.assistant.market.calendar())
        binding = self._binding(stock, data)
        model = select_economic_model(binding['industry'], [], None)
        evidence = [dict(id=f['fact_id'], source=f['source'], content=json.dumps(f, ensure_ascii=False)) for f in facts]
        evidence += [dict(id=f['fact_id'], source=f['source'], content=json.dumps(f, ensure_ascii=False)) for f in data.get('facts', [])]
        evidence += [dict(id=d['id'],source=d['source'],content=json.dumps(d,ensure_ascii=False)) for d in data.get('distributions', [])]
        evidence.append(dict(id='VALUE_HISTORY',source='已保存估值日与报表',content=json.dumps(dict(normalization=view['normalization'],valuation_history=view['valuation_history']),ensure_ascii=False)))
        for e in data.get('events', []):
            evidence.append(dict(id=e['id'], source=e.get('source'), content=json.dumps(e, ensure_ascii=False)[:6000]))
        target = self._peer_row(stock, data, model, view, binding['industry'])
        candidates = []
        industry = binding['industry']
        peer_codes = self.assistant.market.repo.members(self.profile, industry['sector_id']).get('codes', []) if industry else []
        for peer in peer_codes[:501]:
            if peer == code:
                continue
            pdata = self._data(peer)
            pstock = self.assistant.market.repo.stock(self.profile, peer)
            if not pstock or not pdata or pdata.get('source_signature') != binding['source_signature']:
                continue
            pview = build_financial_view(pdata.get('value_facts', []), cutoff)
            candidates.append(self._peer_row(pstock, pdata, model, pview, industry))
        previous_a = self._latest('value_assumptions', code) or {}
        peers = build_peer_comparison(target, candidates, previous_a.get('peer_confirmations', []))
        evidence.append(dict(id='VALUE_PEERS',source='已保存同行候选资料（主营可比性须另行核实）',
            content=json.dumps(peers,ensure_ascii=False)))
        cases = self._case_library(code, cutoff)
        if cases:
            evidence.append(dict(id='VALUE_CASES', source='已保存的可比事件研究', content=json.dumps(cases[:20], ensure_ascii=False)))
        missing = []
        cached_disclosures=next((c for c in data.get('coverage',[]) if c.get('category')=='disclosures' and c.get('cached')),None)
        if cached_disclosures:
            missing.append(f"公告接口本次失败；使用 {cached_disclosures.get('cached_at') or '此前'} 已保存公告，最新披露完整性待核实")
        if not facts:
            missing.append('未取得可核对的三大财务报表；请更新资料或带原文补充')
        if not view.get('current_capital'):
            missing.append('当前总股数未核实；旧年报、流通股数/注册资本不能替代当前股本，请用免费个股资料或原文核对')
        if model['model'] == 'unresolved':
            missing.append('行业或主营经济模型尚未识别，暂停数值估值')
        if not data.get('distributions'):
            missing.append('尚无分红送转明细；更新价值资料可取免费详情，DDM仍需核对未来分配与资本约束')
        binding.update(quote=self._quote(stock), shares=view.get('current_capital') or view['latest'].get('shares'), peer_hash=digest(peers),
                       supplement_hash=digest(facts[len(data.get('value_facts', [])):]))
        snapshot_id = digest(dict(version=VERSION, code=code, facts=facts, binding=binding,
                                  evidence=evidence, valuation_date=cutoff[:10]))
        current = self._latest('value_snapshot', code)
        if current and current['snapshot_id'] == snapshot_id:
            return current
        snapshot = ValueSnapshot(snapshot_id=snapshot_id, code=code, name=stock['name'], cutoff=cutoff,
            facts=facts, financial_view=view, economic_model=model, peers=peers, evidence=evidence,
            events=data.get('events', []), distributions=data.get('distributions', []), cases=cases, binding=binding, missing=missing).model_dump()
        self.assistant.repo.append(self.profile, 'value_snapshot', self.key(code), snapshot)
        return snapshot

    def _stale(self, snapshot, stock):
        if not snapshot:
            return []
        binding = self._binding(stock, self._data(stock['code']))
        reasons = []
        for key, label in [('source_signature', '数据来源配置'), ('eligibility', '证券资格或重大风险'),
                           ('facts_hash', '财报/股本'), ('industry', '行业归属'), ('historical_context_hash', '历史估值/分配/事件案例'), ('evidence_hash', '研究证据'), ('disclosure_coverage_hash','公告覆盖及新鲜度')]:
            if snapshot['binding'].get(key) != binding.get(key):
                reasons.append(label+'已变化，旧报告仅作历史对照')
        if snapshot['version'] != VERSION:
            reasons.append('估值规则版本已更新')
        capital = snapshot['financial_view'].get('current_capital') or {}
        quote = self._quote(stock)
        if capital and quote.get('valid') and capital.get('period', '') < quote.get('trade_date', ''):
            reasons.append('当前报价日期已超出股本核对日期，请更新价值资料')
        return reasons

    def _peer_progress(self, code):
        state = self.assistant.market.repo.get_state(self.profile, 'research_peers:'+code, {})
        counts = dict(total=0, pending=0, running=0, complete=0, failed=0)
        signature = source_signature(self.assistant.settings)
        for identity in state.get('task_ids', []):
            task = self.assistant.market.repo.task(identity)
            if not task or source_signature(AssistantSettings.model_validate(task['payload']['settings'])) != signature:
                continue
            counts['total'] += 1
            if task['state'] in counts:
                counts[task['state']] += 1
        return counts

    def _eta(self, model, elapsed):
        samples = [r['payload']['elapsed_seconds'] for r in self.assistant.repo.records(self.profile,'value_review',limit=60)
            if r['key'].startswith(self.profile+':') and r['payload'].get('model') == model
            and r['payload'].get('status') in ('complete','partial')
            and isinstance(r['payload'].get('elapsed_seconds'),(int,float)) and r['payload']['elapsed_seconds']>0]
        if len(samples)<3:
            return None
        # Empirical observed span, not a promise about model progress.
        return [round(max(0,min(samples)-elapsed)),round(max(0,max(samples)-elapsed))]

    @settings_locked
    def get(self, code):
        stock = self._stock(code)
        snapshot, report, assumptions = [self._latest(kind, code) for kind in ('value_snapshot', 'value_report', 'value_assumptions')]
        reasons = self._stale(snapshot, stock)
        status = 'missing' if snapshot is None else 'stale' if reasons else 'ready'
        task_state = self.assistant.market.repo.get_state(self.profile, 'value_task:'+code, {})
        task = self.assistant.market.repo.task(task_state.get('id')) if task_state.get('id') else None
        data_state = self.assistant.market.repo.get_state(self.profile, 'value_data_task:'+code, {})
        data_task = self.assistant.market.repo.task(data_state.get('id')) if data_state.get('id') else None
        if data_task and data_task['state'] in ('pending', 'running'):
            status = 'preparing'
        peers = self._peer_progress(code)
        if peers['pending'] or peers['running']:
            status = 'preparing'
        if task and task['state'] in ('pending', 'running'):
            status = 'running'
        elif task and task['state'] == 'failed' and status not in ('preparing','stale'):
            status = 'failed'
        if report:
            report = deepcopy(report)
            if not snapshot or report['snapshot_id'] != snapshot['snapshot_id'] or reasons or (assumptions and report['assumptions_revision'] != assumptions['revision']):
                report.update(valuation_state='stale', stale_reasons=reasons or ['资料或假设版本已变化'])
                report['comparison']['conditional_price'] = None
            elif report.get('valuation_state')!='reference' and report.get('parameter_origin')!='reference_sensitivity_v1':
                conservative = next((c.get('value_per_share') for c in report['valuation_cases'] if c['method'] == report['primary_method'] and c['scenario'] == 'conservative' and c['state'] == 'ready'), None)
                report['comparison'] = compare_price(conservative, self._quote(stock), (assumptions or {}).get('margin_required'),
                    dict(eligible=report['valuation_state'] == 'conditional' and self._eligibility(stock)['eligible']))
        review = self._latest('value_review', code)
        historical_review = None
        if review:
            current_model = self.assistant.settings.model
            if not current_model:
                from src.config import get_config
                current_model = get_config().litellm_model or ''
            if (reasons or not snapshot or review.get('snapshot_id') != snapshot['snapshot_id']
                or review.get('published_revision') != (assumptions or {}).get('revision', 0)
                or review.get('model') != current_model):
                historical_review, review = review | dict(stale_reason='资料、假设或模型已变化，旧AI观点仅作历史对照'), None
        if review and review.get('status') in ('failed', 'interrupted') and status not in ('preparing', 'running'):
            status = review['status']
        progress = self.assistant.market.repo.get_state(self.profile, 'value_progress:'+code, {})
        if status == 'ready' and not review and not report:
            progress = dict(phase='prepared', percent=45, message='资料已准备，尚未调用AI；点击生成价值研究继续', eta_seconds=None)
        if status == 'preparing':
            fraction = peers['complete']/peers['total'] if peers['total'] else 0
            progress = dict(phase='preparing', percent=round(10+fraction*35),
                message=f'正在准备财报及候选同行：{peers["complete"]}/{peers["total"]}家完成；失败{peers["failed"]}家', eta_seconds=None)
        if task and task['state'] in ('pending', 'running'):
            elapsed = max(0, (datetime.now(timezone.utc)-datetime.fromisoformat(task['updated_at'])).total_seconds())
            progress = progress | dict(elapsed_seconds=elapsed, eta_seconds=self._eta(task['payload']['settings'].get('model'),elapsed))
        history = []
        for record in self.assistant.repo.records(self.profile,'value_report',limit=12,key=self.key(code)):
            old = record['payload']
            if report and old['snapshot_id']==report['snapshot_id'] and old['assumptions_revision']==report['assumptions_revision']:
                continue
            history.append({k:old.get(k) for k in ('snapshot_id','assumptions_revision','generated_at','primary_method','valuation_cases','valuation_state','parameter_origin')})
        reference=None
        if snapshot and not reasons and not report and status=='ready' and review and review.get('status')=='partial':
            from src.services.a_share_value_reference import build_value_reference
            reference=build_value_reference(snapshot)
            if reference['state']=='ready':
                progress=progress|dict(message='AI完整估值未形成；已提供可编辑参数试算，不额外调用模型')
        return dict(code=code, status=status, snapshot=snapshot, report=report, assumptions=assumptions,reference=reference,
            review=review, historical_review=historical_review, history=history, stale_reasons=reasons, progress=progress,
            data_task={k: data_task[k] for k in ('id', 'state', 'error')} if data_task else None,
            task={k: task[k] for k in ('id', 'state', 'error')} if task else None,
            quote=self._quote(stock), demo=self.profile == 'demo',
            peer_progress=peers,
            message='查看与计算不调用AI；确认假设不等于证明估值正确')

    def _require_snapshot(self, code, identity):
        snapshot = self._latest('value_snapshot', code)
        if not snapshot or snapshot['snapshot_id'] != identity or self._stale(snapshot, self._stock(code)):
            raise ValueConflict('资料版本已变化或尚未准备，请重新读取并核对')
        return snapshot

    @settings_locked
    def prepare(self, code, peer_offset=0, refresh=False):
        self._stock(code)
        if self.profile == 'demo':
            return dict(accepted=False, status='missing', message='演示模式不抓取真实价值资料')
        settings = self.assistant.settings.model_copy(deep=True)
        previous = self.assistant.market.repo.get_state(self.profile, 'value_data_task:'+code, {})
        existing = self.assistant.market.repo.task(previous.get('id')) if previous.get('id') else None
        if (existing and existing['state'] in ('pending', 'running') and existing['payload'].get('peer_offset') == peer_offset
            and configuration_stamp(AssistantSettings.model_validate(existing['payload']['settings'])) == configuration_stamp(settings)):
            return dict(accepted=False, status='preparing', task_id=existing['id'], message='相同价值资料任务正在准备，未重复抓取')
        nonce = self.now() if refresh else self.now()[:10]
        identity = self.assistant.integrated.jobs.submit(self.profile,
            f'value-data:{code}:{peer_offset}:{configuration_stamp(settings)}:{nonce}', 'research_data',
            dict(code=code, root_code=code, peer_offset=peer_offset, settings=settings.model_dump(), include_peers=True, value_only=True), 35)
        self.assistant.market.repo.set_state(self.profile, 'value_data_task:'+code, dict(id=identity))
        self.assistant.market.repo.set_state(self.profile, 'value_progress:'+code, dict(phase='preparing',percent=0,message='排队补齐财报与股本，未调用AI',eta_seconds=None))
        return dict(accepted=True, status='preparing', task_id=identity, message='排队补齐财报、公告和一批候选同行；不调用AI')

    @settings_locked
    def save_assumptions(self, code, request):
        snapshot = self._require_snapshot(code, request.snapshot_id)
        a = request.assumptions.model_dump()
        if a['code'] != code or a['snapshot_id'] != snapshot['snapshot_id']:
            raise ValueError('假设股票或资料版本不一致')
        pairs = [(c.get('method'), c.get('scenario')) for c in a['cases']]
        if len(pairs) != len(set(pairs)):
            raise ValueError('同一估值方法的情景重复，不能覆盖已有情景')
        override = a.get('economic_model_override')
        if override:
            from src.services.a_share_value_peers import PROFILES
            ids = {e['id'] for e in snapshot['evidence']}
            if (override.get('model') not in PROFILES or not override.get('reason') or
                not override.get('evidence_ids') or not set(override['evidence_ids']) <= ids):
                raise ValueError('人工经济模型修正须有当前资料来源、理由及受支持模型')
        from urllib.parse import urlsplit
        for peer in a['peer_confirmations']:
            if not peer.get('attested'):
                peer['evidence_ids'] = []
                continue
            url = peer.get('business_source_url', '')
            parsed = urlsplit(url)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or len(url) > 2000 or
                not isinstance(peer.get('reason'), str) or not 3 <= len(peer['reason']) <= 1000 or
                peer.get('code') not in {p['code'] for p in snapshot['peers']['candidates']}):
                raise ValueError('同行主营确认需有效原文网址、可比理由和当前候选证券')
            peer['evidence_ids'] = ['USER_PEER_'+digest([peer['code'], url, peer['reason']])[:16]]
        from src.repositories.a_share_repository import AssistantRepository
        repo = self.assistant.repo
        with repo.engine.connect() as conn:
            # SQLite's write reservation serializes revisions across worker processes.
            conn.exec_driver_sql('BEGIN IMMEDIATE')
            previous = conn.execute(select(JOURNAL.c.payload).where(JOURNAL.c.mode == AssistantRepository.namespace(self.profile),
                JOURNAL.c.kind == 'value_assumptions', JOURNAL.c.key == self.key(code)).order_by(JOURNAL.c.id.desc()).limit(1)).scalar()
            revision = json.loads(previous)['revision'] if previous else 0
            if revision != request.expected_revision:
                conn.rollback()
                raise ValueConflict('假设版本已被另一窗口更新，请重新读取')
            a.update(revision=revision+1, confirmed=request.confirmed)
            for case in a['cases']:
                case['start_date'] = snapshot['cutoff'][:10]
            a = ValueAssumptions.model_validate(a).model_dump()
            conn.execute(JOURNAL.insert().values(mode=AssistantRepository.namespace(self.profile), kind='value_assumptions',
                key=self.key(code), created_at=utc_now(), payload=json.dumps(a, ensure_ascii=False, allow_nan=False)))
            conn.commit()
        return a

    @settings_locked
    def supplement(self, code, request):
        self._require_snapshot(code, request.snapshot_id)
        now = self.now()
        items = self.assistant.repo.latest(self.profile, 'value_supplements', key=self.key(code), default=[])
        forbidden = {'identity', 'identity_verified', 'st', 'major_risk', 'permissions'}
        for item in request.facts:
            f = item.model_dump()
            supersedes = f.get('supersedes_fact_id')
            if supersedes:
                previous = next((v for v in items if v['fact_id'] == supersedes), None)
                if (not previous or previous['vintage_quality'] != 'user_attested' or previous['metric'] != f['metric']
                    or any(v.get('supersedes_fact_id') == supersedes for v in items)):
                    raise ValueError('只能更正当前有效的同指标人工资料，不能覆盖供应商或已更正记录')
            if f['metric'] in forbidden or f['report_period'] > now[:10] or not stamp(f['published_at']) or stamp(f['published_at']) > now:
                raise ValueError('不能补充未来事实、证券资格或权限')
            period = stamp(f['report_period'])
            if not period:
                raise ValueError('报告期无效')
            content = digest(f)
            item = ValueFact(fact_id='VU'+content[:20], content_hash=content, code=code,
                metric=f['metric'], value=f['value'], unit=f['unit'], report_period=period[:10], period_end=period[:10],
                period_basis=f['period_basis'], scope=f['scope'], attribution=f['attribution'],
                source='user_attested/'+f['title'], raw_field=f['metric'], published_at=stamp(f['published_at']),
                observed_at=now, available_at=now, vintage_quality='user_attested', url=f['url'], quote=f['quote'],
                supersedes_fact_id=supersedes).model_dump()
            if item['fact_id'] not in {v['fact_id'] for v in items}:
                items.append(item)
        self.assistant.repo.append(self.profile, 'value_supplements', self.key(code), items)
        return self.capture(code)

    @settings_locked
    def evaluate(self, code, request):
        snapshot = deepcopy(self._require_snapshot(code, request.snapshot_id))
        assumptions = self._latest('value_assumptions', code)
        if not assumptions or assumptions['revision'] != request.assumptions_revision or assumptions['snapshot_id'] != request.snapshot_id:
            raise ValueConflict('假设版本已变化，请核对最新版本')
        snapshot['binding']['quote'] = self._quote(self._stock(code))
        if assumptions.get('economic_model_override'):
            snapshot['economic_model'] = select_economic_model(snapshot['binding'].get('industry'), [], assumptions['economic_model_override'])
            snapshot['missing'] = [m for m in snapshot['missing'] if not m.startswith('行业或主营经济模型尚未识别')]
        snapshot['peers'] = build_peer_comparison(snapshot['peers']['target'], snapshot['peers']['candidates'], assumptions.get('peer_confirmations', []))
        changes = apply_driver_changes(snapshot, assumptions)
        result = evaluate_value(assumptions | dict(cases=changes['cases']), snapshot)
        result['generated_at'] = self.now()
        if changes['effects']:
            original = evaluate_value(assumptions | dict(driver_changes=[]), snapshot)
            result['driver_effects'] = [dict(changes=changes['effects'], counterfactual=original['valuation_cases'], with_events=result['valuation_cases'])]
        if changes['rejected']:
            result['missing'] += [r['reason'] for r in changes['rejected']]
            result['valuation_state'] = 'review_required'
            result['comparison']['conditional_price'] = None
        for h in assumptions['holding_cases']:
            case = next((c for c in changes['cases'] if c.get('method') == (h.get('method') or assumptions['primary_method']) and c.get('scenario') == h.get('scenario', 'base')), None)
            v = next((v for v in result['valuation_cases'] if case and v['method'] == case['method'] and v['scenario'] == case['scenario']), {})
            if case:
                holding_inputs = {k:h[k] for k in ('realization_factor', 'costs_per_share') if h.get(k) is not None}
                result['holding_cases'].append(evaluate_holding(case | holding_inputs | dict(price=snapshot['binding']['quote'].get('price')), v, snapshot['cutoff'][:10], h.get('months')))
        self.assistant.repo.append(self.profile, 'value_report', self.key(code), result)
        return result

    @settings_locked
    def generate(self, code, request):
        self._require_snapshot(code, request.snapshot_id)
        peers = self._peer_progress(code)
        if peers['pending'] or peers['running']:
            raise ValueConflict('候选同行资料尚在准备，完成后可按固定版本发起一次研究')
        # The paid orchestration is added separately; no silent fallback to other workflows.
        return self._enqueue_research(code, request)

    def handle_task(self, task):
        return self._run_research_task(task)

    def _enqueue_research(self, code, request):
        settings = self.assistant.settings.model_copy(deep=True)
        if not settings.research_enabled:
            raise ValueError('请在设置中启用增强研究；手动假设与计算仍可使用')
        if not settings.model:
            from src.config import get_config
            settings.model = get_config().litellm_model or ''
        if not settings.model:
            raise ValueError('请在原设置页配置研究模型')
        assumptions = self._latest('value_assumptions', code)
        revision = (assumptions or {}).get('revision', 0)
        review = self._latest('value_review', code) or {}
        if not request.force and review.get('snapshot_id') == request.snapshot_id and review.get('model') == settings.model and review.get('published_revision') == revision and review.get('status') in ('complete', 'partial'):
            return dict(accepted=False, status='ready', cached=True, expected_calls=0, message='相同资料与假设的价值研究可直接查看')
        payload = dict(code=code, snapshot=deepcopy(self._latest('value_snapshot', code)),
                       settings=settings.model_dump(), assumptions_revision=revision)
        fingerprint = digest([code, request.snapshot_id, settings.model, revision, configuration_stamp(settings)])
        result = self.assistant.market.repo.enqueue_value_research(self.profile, fingerprint, payload, request.force)
        self.assistant.market.repo.set_state(self.profile, 'value_task:'+code, dict(id=result['task_id']))
        if result['accepted']:
            self.assistant.market.repo.set_state(self.profile, 'value_progress:'+code, dict(phase='queued',percent=0,message='等待一次价值模型复核',eta_seconds=None))
        return result | dict(expected_calls=1 if result['accepted'] else 0,
                             message='价值研究最多一次模型请求；手动调用不限日次数，按实际用量计费')

    def _run_research_task(self, task):
        from src.services.a_share_value_research import ValueResearchEngine
        from src.services.a_share_research import research_failure_message
        from src.schemas.a_share_value import SaveValueRequest, EvaluateValueRequest
        payload, code = task['payload'], task['payload']['code']
        settings = AssistantSettings.model_validate(payload['settings'])
        snapshot = payload['snapshot']
        profile, key = task['profile'], task['profile']+':'+code
        def current():
            latest = self._latest('value_snapshot', code) or {}
            assumptions = self._latest('value_assumptions', code) or {}
            current_model = self.assistant.settings.model
            if not current_model:
                from src.config import get_config
                current_model = get_config().litellm_model or ''
            return (profile == self.profile and source_signature(settings) == source_signature(self.assistant.settings)
                    and self.assistant.settings.research_enabled and settings.model == current_model
                    and latest.get('snapshot_id') == snapshot['snapshot_id']
                    and assumptions.get('revision', 0) == payload['assumptions_revision'])
        def progress(value):
            pointer = self.assistant.market.repo.get_state(profile, 'value_task:'+code, {})
            if pointer.get('id') == task['id']:
                self.assistant.market.repo.set_state(profile, 'value_progress:'+code, value)
        with self.assistant._settings_lock:
            if not current():
                return
            attempt = self.assistant.market.repo.begin_value_attempt(task, snapshot['snapshot_id'])
            if attempt == 'claim_lost':
                return
            if attempt == 'attempted':
                self.assistant.repo.append(profile, 'value_review', key, dict(code=code, snapshot_id=snapshot['snapshot_id'],
                    model=settings.model, published_revision=payload['assumptions_revision'],
                    status='interrupted', missing=['上一次付费请求结果未知，未自动重试；需要时手动重新生成']))
                progress(dict(phase='interrupted', percent=100, message='上次请求中断，未重复收费', eta_seconds=None))
                return
        try:
            review = ValueResearchEngine(self.assistant.repo).run(snapshot, settings, progress)
        except Exception as exc:
            review = dict(code=code, snapshot_id=snapshot['snapshot_id'], model=settings.model,
                          status='failed', missing=[research_failure_message(exc)])
        with self.assistant._settings_lock:
            with self.assistant.market._publication(task):
                if not current():
                    self.assistant.repo.append(profile, 'value_review_history', task['id'], review)
                    progress(dict(phase='obsolete', percent=100, message='配置或假设已变化，旧请求仅保存历史，未覆盖当前研究', eta_seconds=None))
                    return
                proposed = review.get('proposed_assumptions')
                if proposed:
                    try:
                        progress(dict(phase='calculating',percent=85,message='校验拟议假设并进行确定性估值，不再请求模型',eta_seconds=None))
                        saved = self.save_assumptions(code, SaveValueRequest(snapshot_id=snapshot['snapshot_id'],
                            expected_revision=payload['assumptions_revision'], assumptions=proposed, confirmed=False))
                        self.evaluate(code, EvaluateValueRequest(snapshot_id=snapshot['snapshot_id'], assumptions_revision=saved['revision']))
                        review['published_revision'] = saved['revision']
                    except ValueError:
                        review.setdefault('missing', []).append('拟议假设无法计算或版本已变化，未作为有效估值发布')
                review.setdefault('published_revision', payload['assumptions_revision'])
                progress(dict(phase='saving',percent=97,message='保存报告与依据版本',eta_seconds=None))
                self.assistant.repo.append(profile, 'value_review', key, review)
                progress(dict(phase=review['status'], percent=100,
                    message=('价值研究失败，请查看模型错误原因' if review['status']=='failed' else '价值研究已结束；'+('已保存待核对草案' if proposed else '依据不足，查看具体缺口')),
                    elapsed_seconds=review.get('elapsed_seconds'), eta_seconds=None))
