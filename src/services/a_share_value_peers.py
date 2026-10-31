"""Economic-model routing and peer statistics; candidates are not confirmed peers."""
from statistics import median, quantiles

PROFILES = {
    'bank': ('银行', ['rim', 'ddm'], ['不良与拨备', '净息差', '资本充足与分红约束']),
    'life_insurance': ('寿险', ['ddm', 'nav'], ['偿付能力', '准备金', '新业务与投资风险']),
    'nonlife_insurance': ('财险', ['ddm', 'nav'], ['综合赔付', '准备金', '偿付能力']),
    'securities': ('证券', ['ddm', 'nav'], ['净资本', '客户资金隔离', '自营风险']),
    'asset_management': ('资产管理', ['ddm', 'nav'], ['AUM及费率', '客户留存', '自有投资']),
    'leasing': ('融资租赁', ['ddm', 'nav'], ['信用损失', '期限错配', '融资成本']),
    'asset_holding': ('房地产 控股 多元化经营', ['nav'], ['资产处置折价', '到期债务', '受限资金']),
    'cyclical': ('有色金属 工业金属 铝 铜 贵金属 黄金 煤炭 石油 钢铁 化工 化学 期货 航运', ['fcff', 'fcfe', 'nav'], ['周期高点盈利', '成本位置', '维护资本开支', '完整周期与产能变化']),
    'utility': ('电力 水务 燃气 公用事业', ['ddm', 'fcff', 'fcfe'], ['管制回报', '资本开支', '债务与分红']),
    'growth': ('半导体 软件 计算机 通信设备 生物医药', ['fcff', 'fcfe'], ['研发与再投资', '竞争与替代', '融资和稀释']),
    'operating': ('食品 饮料 白酒 家电 汽车 零部件 家居 服装 纺织 消费 商贸 零售 服务 机械 电子 元件 印刷电路板 包装 造纸 医药 制药 物流', ['fcff', 'fcfe', 'ddm'], ['现金流质量', '应收库存', '资本效率', '客户集中']),
    'early_stage': ('早期亏损', ['nav'], ['现金消耗', '管线成功率', '后续融资']),
}


def select_economic_model(industry, business_evidence, override=None):
    name = (industry or {}).get('name', '')
    model = None
    if override and override.get('reason') and override.get('evidence_ids') and override.get('model') in PROFILES:
        model = override['model']
    elif (industry or {}).get('classification') == 'eastmoney-industry':
        if name in ('保险', '多元金融'):
            model = 'unresolved'
        else:
            model = next((k for k, (names, _, _) in PROFILES.items() if any(word in name for word in names.split())), None)
    methods, risks = PROFILES.get(model, ('', [], ['需先核实主营及经济模型；不能自动套用通用估值']))[1:]
    return dict(model=model or 'unresolved', industry=name, allowed_methods=methods, checklist=risks,
                mapping_version='eastmoney-industry-value-v1', evidence_ids=[e.get('id') for e in business_evidence if e.get('id')],
                identification='manual' if override and model else 'industry_candidate')


def build_peer_comparison(target, candidates, confirmations):
    confirmed = {p['code'] for p in confirmations if p.get('evidence_ids')}
    accepted, excluded = [], []
    for p in candidates:
        reason = None
        if p['code'] == target['code']:
            reason = '排除自身'
        elif not p.get('verified') or not target.get('verified') or not p.get('industry_id') or p.get('industry_id') != target.get('industry_id'):
            reason = '行业归属未核实或不一致'
        elif p.get('economic_model') != target.get('economic_model') or p.get('economic_model') == 'unresolved':
            reason = '经济模型不一致或待识别'
        elif not p.get('period') or p.get('period') != target.get('period'):
            reason = '财报期间未对齐'
        elif p['code'] not in confirmed:
            reason = '主营可比证据尚未确认'
        if reason:
            excluded.append(dict(code=p['code'], reason=reason))
        else:
            accepted.append(p)
    metrics = {}
    for field in ('pe', 'pb', 'roe', 'operating_margin', 'cash_yield'):
        target_basis = target.get('metric_basis', {}).get(field, {})
        values, metric_excluded = [], []
        target_valid = (target.get('metrics', {}).get(field) is not None and
            (field not in ('pe','pb') or target['metrics'][field] > 0) and
            (field != 'pb' or (target.get('parent_equity') or 0) > 0) and
            all(target_basis.get(k) for k in ('date','definition','source')))
        for p in accepted:
            basis = p.get('metric_basis', {}).get(field, {})
            value = p.get('metrics', {}).get(field)
            if (not target_valid or not all(basis.get(k) for k in ('date','definition','source'))
                or any(basis[k] != target_basis[k] for k in ('date','definition','source'))):
                reason = '指标估值日、定义或来源未对齐'
            elif value is None or (field in ('pe','pb') and value <= 0) or (field == 'pb' and (p.get('parent_equity') or 0) <= 0):
                reason = '指标缺失、非正PE或非正净资产PB不适用'
            else:
                values.append(value)
                continue
            metric_excluded.append(dict(code=p['code'],reason=reason))
        target_value = target.get('metrics', {}).get(field)
        qualified = len(values) >= 5 and target_value is not None and (field != 'pe' or target_value > 0)
        qs = quantiles(values, n=4, method='inclusive') if len(values) >= 5 else None
        metrics[field] = dict(n=len(values), median=median(values) if values else None,
            q1=qs[0] if qs else None, q3=qs[2] if qs else None,
            percentile=sum(v <= target_value for v in values)/len(values) if qualified else None,
            basis=target_basis, excluded=metric_excluded,
            reason='' if qualified else '同口径正式样本不足5家或目标指标不适用')
    return dict(target=target, candidates=candidates, confirmed=accepted, excluded=excluded, metrics=metrics,
                limitation='相对便宜不等于绝对低估；当前行业成员不能用于历史时点比较')
