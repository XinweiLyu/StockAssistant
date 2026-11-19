import type {WorkspaceMarket} from '../../api/marketWorkspace';
export default function MarketSelector({market,onChange}:{market:WorkspaceMarket;onChange:(market:WorkspaceMarket)=>void}){
 return <div className="am-market-selector" role="group" aria-label="交易市场">{([['cn','A 股'],['hk','港股'],['us','美股']] as const).map(([key,label])=><button className="am-button" key={key} aria-pressed={market===key} onClick={()=>onChange(key)}>{label}</button>)}</div>;
}
