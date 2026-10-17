import { LineChart,Line,XAxis,YAxis,Tooltip,ResponsiveContainer } from 'recharts';
import { normalizedComparison } from './priceChartData';
import type { MarketBar } from '../../types/aShareMarket';
export default function SectorComparisonChart({sector,benchmark,stock}:{sector:MarketBar[];benchmark:MarketBar[];stock?:MarketBar[]}){
  const series=[{name:'板块',items:sector},{name:'沪深300',items:benchmark}];if(stock?.length)series.push({name:'所选股票',items:stock});
  const data=normalizedComparison(series);
  if(!data.length)return <p className="as-footnote">缺少共同有效日期或沪深300历史，暂不能比较。板块实际历史仍在上方显示。</p>;
  return <div><p className="as-footnote">首个共同交易日 = 100 · 仅比较共同日期，不插值 · {data[0].date} 至 {data.at(-1)?.date}</p><div className="am-comparison"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><XAxis dataKey="date" minTickGap={50} tick={{fontSize:10}}/><YAxis domain={['auto','auto']} width={48} tick={{fontSize:10}}/><Tooltip/>{series.map((s,i)=><Line key={s.name} name={s.name} dataKey={s.name} stroke={['#e3ac57','#a8c9fa','#b996ec'][i]} dot={false} strokeWidth={1.5}/>)}</LineChart></ResponsiveContainer></div></div>;
}
