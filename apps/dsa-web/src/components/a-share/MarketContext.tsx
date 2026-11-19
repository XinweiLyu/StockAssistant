import {createContext,useContext} from 'react';
import type {WorkspaceMarket} from '../../api/marketWorkspace';
export const MarketContext=createContext<{market:WorkspaceMarket;currency:string;financialCurrency:string}>({market:'cn',currency:'CNY',financialCurrency:'CNY'});
export const useMarketPresentation=()=>useContext(MarketContext);
export const currencyLabel=(currency:string)=>({CNY:'人民币',HKD:'港元',USD:'美元'}[currency]||currency);
export const currencyMark=(currency:string)=>({CNY:'¥',HKD:'HK$',USD:'US$'}[currency]||currency+' ');

export const currencyUnit=(currency:string)=>currency==='CNY'?'元':currencyLabel(currency);
