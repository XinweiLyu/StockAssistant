import {useState} from 'react';
import apiClient from '../../api';
import {instrumentBase} from '../../api/marketWorkspace';

export default function ListingBindingEditor({code,onSaved}:{code:string;onSaved:()=>void}){
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 return <details className="am-evidence"><summary>核实上市股权、ADR与报价币种换算</summary>
  <p>财报币种与报价币种可能不同。每一上市单位对应的基础普通股、实际股数及后续资本行动须有原文依据；未核实前保留企业研究，暂停上市每股安全价。</p>
  <form className="as-form" onSubmit={e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);setBusy(true);setMessage('');
   const payload={underlying_per_listed:Number(data.get('ratio')),issued_shares:data.get('shares')?Number(data.get('shares')):null,
    effective_date:String(data.get('effective')),verified_through:String(data.get('through')),url:String(data.get('url')),
    quote:String(data.get('quote')),reason:String(data.get('reason')),confirmed:true};
   void apiClient.put(instrumentBase(code)+'/stocks/'+encodeURIComponent(code)+'/listing-binding',payload).then(()=>{setMessage('已保存有来源的核实记录；请更新价值资料后重新计算。');onSaved();}).catch(()=>setMessage('核实记录未保存，请检查来源、日期、股数及汇率可用性。')).finally(()=>setBusy(false));
  }}>
   <div className="am-value-form-grid">
    <label>每上市单位对应基础普通股数<input name="ratio" type="number" min="0.000001" step="any" required/></label>
    <label>已发行基础普通股数（非加权平均，可选）<input name="shares" type="number" min="1" step="any"/></label>
    <label>股权／股数生效日<input name="effective" type="date" required/></label>
    <label>资本行动已核实至<input name="through" type="date" required/></label>
    <label>公司／存托行／申报原文网址<input name="url" type="url" required/></label>
   </div>
   <label>支持股权比例与股数的原文<textarea name="quote" minLength={3} maxLength={2000} required/></label>
   <label>核实范围和理由<textarea name="reason" minLength={3} maxLength={1000} required/></label>
   <label><input type="checkbox" required/>我已核实证券类别、比例方向、库存股与生效日后的发行／回购／拆合股；不是仅按代码猜测</label>
   <button className="am-button" disabled={busy}>{busy?'保存中…':'保存核实并获取有日期的汇率（不调用AI）'}</button>
   {message&&<p role="status">{message}</p>}
  </form>
 </details>;
}
