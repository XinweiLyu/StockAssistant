"""Hard validation for explicitly uncalibrated, referenced scenario research."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
import re
from pydantic import ValidationError
from src.schemas.a_share_integrated import IntegratedForecast, IntegratedPlan, canonical_plan_day
from src.services.a_share_event_cases import finite, effective_event_families

UNSAFE = re.compile(r'概率|胜率|保证.*?(?:收益|盈利)|保本|必涨|稳赚|仓位|股数|下单|立即买|立即卖|\b(?:probability|quantity|guarantee|order)\b', re.I)


def tick_price(value, rounding=ROUND_HALF_UP):
    try:
        return float(Decimal(str(value)).quantize(Decimal('.01'),rounding=rounding))
    except InvalidOperation as exc:
        raise ValueError('价位无法转换为0.01元单位') from exc


def numeric_references(bundle):
    refs = []
    for f in bundle.get('baseline', {}).get('forecasts', []):
        if f.get('horizon_sessions') in (5,20,60) and all(finite(f.get(k)) and f[k] > 0 for k in ('low','median','high')) and f['low'] <= f['median'] <= f['high']:
            refs.append(dict(id='B'+str(f['horizon_sessions']), horizon_sessions=f['horizon_sessions'],
                low=f['low'], median=f['median'], high=f['high'], kind='price_baseline',
                source=bundle.get('source'), method=bundle['baseline'].get('version')))
    for r in bundle.get('cases', {}).get('price_references', []):
        if r.get('horizon_sessions') in (5,20,60) and r.get('sample_size',0) >= 10 and all(finite(r.get(k)) and r[k] > 0 for k in ('low','median','high')):
            refs.append(r)
    return refs


def strategy_candidates(bundle, min_reward_risk):
    base = bundle.get('baseline', {})
    context = bundle.get('context', {})
    reasons = list(base.get('plan', {}).get('reasons', []))
    blocked = (context.get('major_risk') is True or not context.get('identity_verified') or context.get('st') is not False or
               context.get('board') != 'main' or any('重大风险' in r for r in reasons))
    trends = {r['period']:r.get('state') for r in base.get('trends', [])}
    environment = base.get('environment', {})
    long_up = all(trends.get(p) == 'up' for p in (60,120,250)) and base.get('weekly', {}).get('state') == 'up'
    relative = environment.get('relative20')
    trend = long_up and environment.get('market_state') == 'up' and finite(relative) and relative > 0
    range_state = environment.get('market_state') == 'range' and trends.get(250) != 'down' and base.get('weekly', {}).get('state') in ('range','up')
    event = any(e.get('public_verified') and e.get('active_catalyst') and e.get('direction') == 'positive'
                and e.get('extraction_status') != 'withdrawn' for e in effective_event_families(bundle.get('events', [])))
    return [dict(strategy_kind=kind, eligible=bool(condition and not blocked), min_reward_risk=min_reward_risk,
                 reasons=(['身份、市场范围或核实重大风险限制'] if blocked else []))
            for kind,condition in [('trend_pullback',trend),('range_reversion',range_state),('event_followthrough',event)]]


def validate_integrated_prediction(value, bundle, sent_ids, min_reward_risk=2., *, as_of_day=None):
    result = dict(status='insufficient', forecasts=[], plans=[], rejected=0, rejections=[], calibrated=False,
        limitations=['综合价位为研究估计，尚未校准；引用和范围校验不证明经济推导正确',
                     '模型评分及情景覆盖不是胜率；尚未验证综合策略组合收益'])
    if not isinstance(value,dict) or not 1 <= min_reward_risk <= 5:
        return result | dict(rejected=1)
    refs = {r['id']:r for r in numeric_references(bundle) if r['id'] in sent_ids}
    candidates = {r['strategy_kind']:r for r in strategy_candidates(bundle,min_reward_risk)}

    def common(parsed):
        data=parsed.model_dump()
        if 'P1' not in data['sources'] or any(i not in sent_ids for i in data['sources']):
            raise ValueError('引用未发送的资料')
        selected=[refs.get(i) for i in data['basis_ids']]
        if not selected or any(not r or r['horizon_sessions'] != data['horizon_sessions'] for r in selected):
            raise ValueError('期限或数值依据不一致')
        text=' '.join(data['conditions']+data.get('invalidation',[])+[data['derivation']])
        if data.get('second_entry'):
            secondary = data['second_entry']
            text += ' ' + ' '.join(secondary['conditions'] + secondary['invalidation'])
        if any(not t.strip() or len(t)>1000 for t in data['conditions']+data.get('invalidation',[])) or UNSAFE.search(text):
            raise ValueError('不受支持的交易承诺或字段')
        if re.search(r'估值|财报|EPS|市盈率',text,re.I) and not any(i.startswith('F') for i in data['sources']):
            raise ValueError('缺财务依据')
        return data, min(r['low'] for r in selected), max(r['high'] for r in selected)

    for item in (value.get('forecasts') if isinstance(value.get('forecasts'),list) else [])[:9]:
        try:
            data, lower, upper = common(IntegratedForecast.model_validate(item))
            if not lower-1e-8 <= data['low'] <= data['high'] <= upper+1e-8:
                raise ValueError('超出已发送数值参考范围')
            data['low']=max(tick_price(lower,ROUND_CEILING),tick_price(data['low']))
            data['high']=min(tick_price(upper,ROUND_FLOOR),tick_price(data['high']))
            if not lower-1e-8 <= data['low'] <= data['high'] <= upper+1e-8:
                raise ValueError('超出已发送数值参考范围')
            if any((f['horizon_sessions'],f['scenario']) == (data['horizon_sessions'],data['scenario']) for f in result['forecasts']):
                raise ValueError('重复情景')
            result['forecasts'].append(data)
        except (ValidationError,ValueError,TypeError) as exc:
            result['rejected']+=1
            result['rejections'].append(dict(kind='forecast',horizon=item.get('horizon_sessions') if isinstance(item,dict) else None,
                reason=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,ValidationError) else '结构或数值类型不符合约定'))
    for horizon in (5,20,60):
        group=sorted([f for f in result['forecasts'] if f['horizon_sessions']==horizon],key=lambda f:['bear','base','bull'].index(f['scenario']))
        centers=[(f['low']+f['high'])/2 for f in group]
        if centers != sorted(centers):
            result['forecasts']=[f for f in result['forecasts'] if f['horizon_sessions'] != horizon]
            result['rejected']+=len(group)
    for item in (value.get('plans') if isinstance(value.get('plans'),list) else [])[:3]:
        try:
            data, lower, upper = common(IntegratedPlan.model_validate(item))
            for key in ('entry_low','entry_high','stop_reference'):
                if data[key] is not None:
                    data[key]=tick_price(data[key])
            data['targets']=[tick_price(t) for t in data['targets']]
            if data['second_entry']:
                for key in ('low','high'):
                    data['second_entry'][key]=tick_price(data['second_entry'][key])
            expiry_cutoff=date.fromisoformat(bundle['cutoff'][:10])
            if as_of_day is not None:
                expiry_cutoff=max(expiry_cutoff,date.fromisoformat(canonical_plan_day(as_of_day)))
            if date.fromisoformat(data['valid_until']) < expiry_cutoff:
                raise ValueError('计划已过有效期')
            prices=[data['entry_low'],data['entry_high'],data['stop_reference']]
            secondary=data['second_entry']
            lo,hi,stop=prices
            supplied=[p for p in prices if p is not None]+data['targets']
            if secondary:
                supplied.extend((secondary['low'],secondary['high']))
            if any(not finite(p) or p<=0 or not lower-1e-8<=p<=upper+1e-8 for p in supplied):
                raise ValueError('价位超出所引数值参考范围')
            if ((lo is not None and hi is not None and lo>hi) or
                (stop is not None and any(p is not None and p<=stop for p in (lo,hi))) or
                data['targets']!=sorted(data['targets']) or
                (data['targets'] and any(p is not None and p>=data['targets'][0] for p in prices))):
                raise ValueError('价位顺序错误')
            if secondary and (secondary['low']>secondary['high'] or
                (stop is not None and stop>=secondary['low']) or
                (data['targets'] and secondary['high']>=data['targets'][0])):
                raise ValueError('二次买入区间或止损关系错误')
            reasons=[]
            ratio=None
            net_ratio=None
            if any(p is None for p in prices) or not data['targets']:
                reasons.append('缺少完整入场、止损或目标依据')
            else:
                ratio=(data['targets'][0]-hi)/(hi-stop)
                # Conservative one-lot illustration, not an executed or historical cost model.
                from src.services.a_share_rules import DEFAULT_RISK
                unit_cost=2*max(DEFAULT_RISK['minimum_fee']/100,hi*DEFAULT_RISK['commission'])+2*hi*DEFAULT_RISK['transfer_fee']+hi*.002
                net_ratio=(data['targets'][0]-hi-unit_cost)/(hi-stop+unit_cost)
                if data['targets'][0]-hi<=unit_cost or net_ratio<min_reward_risk:
                    reasons.append('成本空间不足：按100股示例、最低佣金及税费/滑点预算估计；实际成交成本未验证')
                if ratio < min_reward_risk:
                    reasons.append('潜在收益/风险不足，未抬高目标价')
                if secondary and (min(data['targets'])-secondary['high'])/(secondary['high']-stop) < min_reward_risk:
                    reasons.append('二次买入条件的潜在收益/风险不足')
                if secondary and (min(data['targets'])-secondary['high']-unit_cost)/(secondary['high']-stop+unit_cost) < min_reward_risk:
                    reasons.append('二次买入条件的成本后收益/风险空间不足')
            chosen=candidates.get(data['strategy_kind'])
            if not chosen or not chosen['eligible']:
                reasons.append('当前市场、长期趋势、事件或风险条件不满足该策略')
            if any(p['horizon_sessions']==data['horizon_sessions'] for p in result['plans']):
                raise ValueError('重复期限计划')
            data.update(status='observe' if reasons or data['status']=='observe' else 'conditional',
                        reward_risk=ratio,net_reward_risk=net_ratio,min_reward_risk=min_reward_risk,rejection_reasons=reasons)
            result['plans'].append(data)
        except (ValidationError,ValueError,TypeError) as exc:
            result['rejected']+=1
            result['rejections'].append(dict(kind='plan',horizon=item.get('horizon_sessions') if isinstance(item,dict) else None,
                reason=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,ValidationError) else '结构或数值类型不符合约定'))
    if result['forecasts'] or result['plans']:
        result['status']='partial' if result['rejected'] else 'ready'
    return result
