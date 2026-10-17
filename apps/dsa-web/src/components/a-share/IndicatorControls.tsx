import type { IndicatorSelection, IndicatorName } from '../../types/aShareMarket';
const NAMES:IndicatorName[]=['MA5','MA10','MA20','MA60','MA120','MA250','BOLL','volume','MACD','RSI','ATR20'];
export default function IndicatorControls({value,onChange}:{value:IndicatorSelection;onChange:(v:IndicatorSelection)=>void}){
  return <fieldset className="am-indicators"><legend>图表指标</legend>{NAMES.map(n=><label key={n}><input type="checkbox" checked={!!value[n]} onChange={e=>onChange({...value,[n]:e.target.checked})}/>{n==='volume'?'成交量':n}</label>)}</fieldset>;
}
