"""Event evidence changes assumptions, never appends a historical price reaction."""
from copy import deepcopy
from src.schemas.a_share_integrated import stamp
from src.services.a_share_value_valuation import number

RATIOS = {'growth', 'ebit_margin', 'da_ratio', 'capex_ratio', 'nwc_ratio', 'tax'}
AMOUNTS = {'after_tax_interest', 'net_borrowing', 'minority_cashflow'}


def apply_driver_changes(snapshot, assumptions):
    s = snapshot.model_dump() if hasattr(snapshot, 'model_dump') else snapshot
    a = assumptions.model_dump() if hasattr(assumptions, 'model_dump') else assumptions
    cases = deepcopy(a.get('cases', []))
    events = {e.get('event_id') or e.get('id'): e for e in s.get('events', [])}
    ids = set(events) | {f['fact_id'] for f in s.get('facts', [])} | {e['id'] for e in s.get('evidence', []) if e.get('id')}
    effects, rejected, used = [], [], set()
    for change in a.get('driver_changes', []):
        try:
            event = events.get(change.get('event_id'))
            if not event or not stamp(event.get('published_at')) or stamp(event['published_at']) > stamp(s['cutoff']):
                raise ValueError('事件来源不存在、时间未知或尚未发生')
            field = change.get('field')
            if field not in RATIOS | AMOUNTS or change.get('unit') != ('ratio' if field in RATIOS else 'CNY'):
                raise ValueError('不支持的经营输入或单位不符；保留定性研究')
            family = event.get('family_id') or change['event_id']
            if change.get('already_in_baseline') is not False:
                raise ValueError('同族同驱动重复，或未确认基准是否已纳入')
            if not change.get('sources') or not set(change['sources']) <= ids or not change.get('rationale'):
                raise ValueError('缺少实际送达的引用及经营传导依据')
            years = change.get('years', [])
            if not years or any(type(y) is not int or not 1 <= y <= 5 for y in years):
                raise ValueError('事件须指定1至5年的作用期间')
            old, new = number(change.get('old'), '事件原值'), number(change.get('new'), '事件新值')
            half_life = number(change.get('half_life_years'), '事件半衰期', .01, 100)
            replacements = []
            for index, case in enumerate(cases):
                if change.get('method') and change['method'] != case.get('method'):
                    continue
                if change.get('scenario') and change['scenario'] != case.get('scenario'):
                    continue
                if not case.get('operating'):
                    continue
                if field in AMOUNTS and case.get('method') != 'fcfe':
                    raise ValueError('该金额输入只适用于FCFE，不能把未使用的输入标为事件传导')
                for year in sorted(set(years)):
                    if (family, field, index, year) in used:
                        raise ValueError('同族同驱动重复作用于同一方法、情景和年份')
                    row = case['operating']['years'][year-1]
                    if abs(number(row.get(field), field)-old) > 1e-9:
                        raise ValueError('事件原值与所选情景基准不一致，请分别提供变更')
                    value = old+(new-old)*2**(-(year-min(years))/half_life)
                    replacements.append((index, year-1, value))
            if not replacements:
                raise ValueError('当前方法无该经营驱动桥接，不能数值叠加事件')
            for index, year, value in replacements:
                cases[index]['operating']['years'][year][field] = value
                used.add((family, field, index, year+1))
            effects.append(dict(**change, family_id=family, applied_years=sorted(set(years)),
                                note='变更当前剩余影响，按显式半衰期衰减；不是事件股价涨幅'))
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append(dict(event_id=change.get('event_id'), reason=str(exc) if isinstance(exc, ValueError) else '事件输入结构不完整'))
    return dict(cases=cases, counterfactual=deepcopy(a.get('cases', [])), effects=effects, rejected=rejected)
