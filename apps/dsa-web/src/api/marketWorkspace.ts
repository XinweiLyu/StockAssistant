import apiClient from './index';
export type WorkspaceMarket='cn'|'hk'|'us';
export const marketBase=(market:WorkspaceMarket)=>market==='cn'?'/api/v1/a-share/market':`/api/v1/market-workspace/${market}`;
export const codeMarket=(code:string):WorkspaceMarket=>code.startsWith('us:')?'us':code.startsWith('hk:')?'hk':'cn';
export const instrumentBase=(code:string)=>marketBase(codeMarket(code));
export const pathBase=(path:string)=>{
 const match=decodeURIComponent(path).match(/^\/(?:stocks|sectors)\/(us|hk):/);
 return marketBase((match?.[1]||'cn') as WorkspaceMarket);
};
export const workspaceWatchlist={
 get:async(market:WorkspaceMarket)=>(await apiClient.get<{codes:string[]}>(`/api/v1/market-workspace/${market}/watchlist`)).data.codes,
 change:async(market:WorkspaceMarket,code:string,remove:boolean)=>(await (remove?apiClient.delete:apiClient.post)(`/api/v1/market-workspace/${market}/watchlist/${encodeURIComponent(code)}`)).data,
};
