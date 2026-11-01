import {useState} from 'react';
import type {ValueStrategy,ValueScenario} from '../../types/aShareValue';
const labels:Record<string,string>={conservative:'较保守历史锚点',base:'中间历史锚点',upside:'较有利历史锚点',
 fact:'现状资料',delivery:'输入送达',assumption:'未来假设',method:'方法适配',revenue:'收入',net_profit:'归母利润',operating_cashflow:'经营现金流',capex:'资本开支',
 pending:'待到期/待披露',matured:'已到期对照',insufficient:'资料不足',breached:'需复核',observed:'本次未触及条件'};
const format=(n?:number|null,unit='CNY')=>n==null||!Number.isFinite(n)?'待补齐':unit==='ratio'?`${(n*100).toFixed(1)}%`:unit==='days'?`${n.toFixed(1)}天`:Math.abs(n)>=1e8?`${(n/1e8).toFixed(2)}亿元`:`${n.toLocaleString('zh-CN',{maximumFractionDigits:2})}元`;
export default function ValueStrategyPanel({strategy:s}:{strategy:ValueStrategy}){
 const [scenario,setScenario]=useState<ValueScenario>('base');const c=s.company_drivers,m=s.monitoring,e=s.expectations;
 const selected=c.projections.find(p=>p.scenario===scenario)||c.projections[0];
 return <section aria-label="经营底稿与持有复核" className="am-value-holding">
  <h4>经营底稿与持有复核</h4><p>质量、经营假设、价格与持有条件分别核查。底稿和公式计算不额外调用AI。</p>
  {s.stale&&<p className="am-integrated-warning">研究底稿已过期；下列为原资料对照，请更新研究后再判断。</p>}
  <details className="am-evidence"><summary>财务质量与资本回报 · 公式及局限</summary>
   <div className="am-value-scroll"><table><thead><tr><th>指标</th><th>数值 / 期间</th><th>公式、来源与待核查</th></tr></thead><tbody>{Object.entries(s.economics.metrics).map(([key,v])=><tr key={key}><th>{v.label}</th><td><span>{format(v.value,v.unit)}</span><br/>{v.period}</td><td>{v.reason||v.formula}<p>{v.limitation}</p><details><summary>查看 {v.fact_ids.length} 项原始依据</summary><small>{v.fact_ids.join('、')||'缺少必要来源'}</small></details></td></tr>)}</tbody></table></div>
   {s.economics.flags.map(f=><p className="am-integrated-warning" key={f.code}>{f.message}</p>)}<p>{s.economics.limitation}</p>
  </details>
  <details className="am-evidence"><summary>公司历史驱动与经营假设起点</summary><p>{c.limitation}</p>
   {c.growth_range&&<p>收入增长样本 {c.growth_range.n} 个；中位锚点 {format(c.growth_range.median,'ratio')}。历史分位不是未来概率。</p>}
   <div className="am-value-scroll"><table><thead><tr><th>年度</th><th>收入</th><th>归母利润</th><th>经营现金</th><th>总投资</th></tr></thead><tbody>{c.history.map((r,i)=><tr key={i}><td>{r.period}</td>{['revenue','net_profit','operating_cashflow','capex'].map(k=><td key={k}>{format(typeof r[k]==='number'?r[k]:null)}</td>)}</tr>)}</tbody></table></div>
   {selected?<><label>经营历史投影情景<select aria-label="经营历史投影情景" value={selected.scenario} onChange={ev=>setScenario(ev.target.value as ValueScenario)}>{c.projections.map(p=><option key={p.scenario} value={p.scenario}>{labels[p.scenario]}</option>)}</select></label><p>{selected.assumption}</p>
    <div className="am-value-scroll"><table><thead><tr><th>未来财务期间</th><th>收入锚点投影</th><th>归母利润</th><th>经营现金</th><th>总投资</th></tr></thead><tbody>{selected.years.map(y=><tr key={y.period}><td>{y.period}</td><td>{format(y.revenue)}</td><td>{format(y.net_profit)}</td><td>{format(y.operating_cashflow)}</td><td>{format(y.capex)}</td></tr>)}</tbody></table></div>
    <p>上述为公司历史数据形成的研究起点，未来量价、竞争、费用和资本需求仍须论证。可在下方假设编辑中记录待验证投影。</p></>:<p>{c.reason||'经营期间或专属业务驱动不足，保留未知。'}</p>}
  </details>
  <details className="am-evidence"><summary>估值方法、增长与终值复核</summary>{s.method_guidance.map(g=><p key={g.method}>{g.method.toUpperCase()}：{g.reason}</p>)}{s.economic_checks.length?s.economic_checks.map((check,i)=><p key={i}>{check.method} {check.scenario} · {check.message}{check.reinvestment_rate!=null&&`；再投资率 ${format(check.reinvestment_rate,'ratio')}`}{check.implied_roic!=null&&`；隐含回报 ${format(check.implied_roic,'ratio')}`}</p>):<p>尚无完整公司假设，不能宣称增长、再投资和终值已通过数值复核。</p>}</details>
  <details className="am-evidence"><summary>价格反推 · 固定其余假设的条件试算</summary>
   <p>{{reference_input:'规则参数参考输入',unverified_input:'价格日期未核实的输入',verified_quote_input:'已核验报价输入'}[e?.price_basis||'']||'资料不足'}</p>
   {e?.input_price!=null&&<p>输入不复权价格：{format(e.input_price)}；基础情景：{e.method?.toUpperCase()} / {e.scenario}（已接受事件及主营修正后）{e.baseline_value!=null&&`；该情景估值 ${format(e.baseline_value)}`}</p>}
   {e?.bracket&&<p>搜索范围：{e.bracket.map(n=>e.parameter?.endsWith('scale')?n.toFixed(3):`${(n*100).toFixed(2)}`).join('—')}{e.parameter?.endsWith('scale')?'倍':'个百分点'}；范围以外不外推</p>}
   {e?.state==='solved'?<p>{({growth_shift:'前5年收入增速平移',roe_shift:'ROE平移',dividend_scale:'股利规模倍数',asset_scale:'资产价值倍数'} as Record<string,string>)[e.parameter||'']||e.parameter}：{e.parameter?.endsWith('scale')?`${e.solution?.toFixed(3)}倍`:`${((e.solution||0)*100).toFixed(2)}个百分点`}</p>:<p>{e?.reason||'公司假设或价格不足，尚不能反推。'}</p>}
   <p>{e?.held_assumptions}</p><p>{e?.limitation||'不识别真实市场共识，不作为买入建议。'}</p>
  </details>
  <details className="am-evidence" open><summary>持有复核与原始经营假设对照</summary>
   <p>下次定期复核：{m?.next_review||'待建立研究'}。估值过高、经营反证、资本配置及组合风险分别判断；价格波动不会自动等同于价值失效。</p>
   {m?.signals.map((signal,i)=><p className="am-integrated-warning" key={i}>{signal.message}</p>)}
   {m?.rules.length?m.rules.map(rule=><p key={rule.id}>{labels[rule.metric]||rule.metric} · {labels[rule.state]||rule.state} · {rule.reason}{rule.review_due&&' · 已到复核日期'}</p>):<p>尚未设置经营失效条件；可在“假设编辑与免费计算”中添加指标、阈值、来源及复核日期。</p>}
   {m?.forward_checks.length?<div className="am-value-scroll"><table><thead><tr><th>指标 / 目标期间</th><th>原始假设</th><th>当前修订实际值</th><th>状态与依据</th></tr></thead><tbody>{m.forward_checks.map((f,i)=><tr key={i}><th>{labels[f.metric]||f.metric} · {f.period}</th><td>{format(f.forecast,f.unit)}</td><td>{format(f.actual,f.unit)}</td><td>{labels[f.state]||f.state}<p>{f.reason}</p><small>{f.vintage}</small></td></tr>)}</tbody></table></div>:<p>暂无已冻结的前瞻记录。未来实际财报到达后才可对照，不用后改参数证明过去准确。</p>}
   <p>组合：{m?.portfolio.state==='available'?`该股占净值 ${format(m.portfolio.stock_weight,'ratio')}`:m?.portfolio.reason||'账户资料不足'}。</p><p>{m?.limitation}</p>
  </details>
  <details className="am-evidence"><summary>资料缺口与假设状态 · 分开处理</summary>{s.gaps.map((g,i)=><p key={i}>[{labels[g.kind]||g.kind}] {g.item}{g.blocks&&`；影响：${g.blocks}`}</p>)}<p>{s.limitation}</p></details>
 </section>;
}
