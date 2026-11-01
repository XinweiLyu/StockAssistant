import {useState} from 'react';
import type {ValueReport,ValueResearchResult} from '../../types/aShareValue';

const money=(n:number)=>`¥${n.toFixed(2)}`;
const percent=(n:number)=>Number.isFinite(n*100)?`${(n*100).toFixed(1)}%`:'计算结果超出范围，请核对输入';
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n);

export default function ValuePriceComparison({report,quote,marginRequired,reference,stale}:{
 report?:ValueReport;quote?:ValueResearchResult['quote'];marginRequired?:number|null;reference:boolean;stale:boolean;
}){
 const [priceInput,setPriceInput]=useState<string|null>(null);
 const [discountInput,setDiscountInput]=useState<string|null>(null);
 if(!reference){
  const c=report?.comparison;
  const reason=stale?'资料已变化，请先更新研究':c?.reason||'尚无通过核验的比较结果，请查看研究状态与具体缺口';
  return <dl className="am-value-comparison">
   <div><dt>对保守价值的安全边际</dt><dd>{!stale&&finite(c?.margin)?percent(c.margin):'暂不可计算'}</dd><small>分母：保守价值</small>{(stale||!finite(c?.margin))&&<small>{reason}</small>}</div>
   <div><dt>到保守价值的潜在涨幅</dt><dd>{!stale&&finite(c?.upside)?percent(c.upside):'暂不可计算'}</dd><small>分母：当前不复权价</small>{(stale||!finite(c?.upside))&&<small>{reason}</small>}</div>
   <div><dt>满足要求折价的条件参考上限</dt><dd>{!stale&&finite(c?.conditional_price)?money(c.conditional_price):'暂停发布'}</dd><small>关键资料、确认或风险不满足时暂停发布</small>{(stale||!finite(c?.conditional_price))&&<small>{reason}</small>}</div>
  </dl>;
 }
 if(stale||report?.valuation_state==='stale')return <p className="am-integrated-warning">资料已变化，请先更新研究</p>;
 if(report?.valuation_state==='disputed')return <p className="am-integrated-warning">试算情景存在争议，请先核对假设</p>;
 const conservative=report?.valuation_cases.find(c=>c.method===report.primary_method&&c.scenario==='conservative'&&c.state==='ready')?.value_per_share;
 const value=finite(conservative)&&conservative>0?conservative:null;
 const cached=finite(quote?.price)&&quote.price>0?quote.price:null;
 const priceText=priceInput??(cached==null?'':String(cached));
 const discountText=discountInput??String(marginRequired==null?25:marginRequired*100);
 const price=priceText.trim()!==''&&Number.isFinite(Number(priceText))&&Number(priceText)>=.01?Number(priceText):null;
 const discount=discountText.trim()!==''&&Number.isFinite(Number(discountText))&&Number(discountText)>=0&&Number(discountText)<=80?Number(discountText)/100:null;
 const priceSource=priceInput!==null?'使用手动输入价格；未作为行情事实保存。':cached==null?'未取得可用价格，请输入试算基准价。':quote?.valid?`使用已核验日期的不复权报价${quote.trade_date?`（${quote.trade_date}）`:''}，可修改。`:`缓存价格日期未核实${quote?.trade_date?`（记录日期${quote.trade_date}）`:''}；仅作为试算输入，可修改。`;
 return <div>
  <div className="am-value-form-grid">
   <label>试算基准价（元，不复权）<input aria-label="试算基准价（元，不复权）" type="number" min="0.01" step="any" value={priceText} onChange={e=>setPriceInput(e.target.value)}/></label>
   <label>试算要求折价 %<input aria-label="试算要求折价 %" type="number" min="0" max="80" step="any" value={discountText} onChange={e=>setDiscountInput(e.target.value)}/></label>
  </div>
  <p>{priceSource} 要求折价为可编辑试算参数{marginRequired==null?'（初始25%）':''}，不代表公司预测。</p>
  <dl className="am-value-comparison" aria-live="polite">
   <div><dt>相对试算值的折价率</dt><dd>{value==null?'较保守试算值不可用':price==null?'请输入有效基准价':percent((value-price)/value)}</dd><small>公式：（较保守试算值－基准价）÷较保守试算值</small></div>
   <div><dt>到试算值的价格差幅</dt><dd>{value==null?'较保守试算值不可用':price==null?'请输入有效基准价':percent((value-price)/price)}</dd><small>公式：（较保守试算值－基准价）÷基准价</small></div>
   <div><dt>要求折价对应价格（试算）</dt><dd>{value==null?'较保守试算值不可用':discount==null?'请输入0–80%的折价比例':money(value*(1-discount))}</dd><small>公式：较保守试算值×（1－要求折价）</small></div>
  </dl>
  <p className="as-footnote">仅为参数试算的算术对照，不是正式安全边际、预期收益或买入价。负数表示基准价高于试算值。修改立即计算，不调用AI、不保存研究假设或改变K线。</p>
 </div>;
}
