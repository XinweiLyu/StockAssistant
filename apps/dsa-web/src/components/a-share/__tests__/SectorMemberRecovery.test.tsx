import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {aShareMarketApi} from '../../../api/aShareMarket';
import type {Sector} from '../../../types/aShareMarket';
import SectorDetail from '../SectorDetail';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{members:vi.fn()}}));
beforeEach(()=>{vi.useFakeTimers();});
afterEach(()=>{cleanup();vi.useRealTimers();vi.clearAllMocks();});
it('shows board-member source errors and the retry button performs a fresh fetch',async()=>{
  const sector={sector_id:'em:industry:BK1586',kind:'industry',name:'软饮料',classification:'eastmoney-industry',source:'akshare/eastmoney'} as Sector;
  vi.mocked(aShareMarketApi.members).mockImplementation(async(_id,params)=>({items:params.refresh?[{code:'000848',name:'承德露露',source:'fixture',quote:null,industries:[],concepts:[]}]:[],total:params.refresh?1:0,page:1,page_size:20,membership:{codes:params.refresh?['000848']:[],version:params.refresh?'v1':null,state:params.refresh?'ready':'failed',error:params.refresh?undefined:'来源不可用'}}));
  render(<SectorDetail sector={sector} onSelectStock={()=>{}} onClose={()=>{}}/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
  expect(screen.getByRole('alert')).toHaveTextContent('来源不可用');
  expect(screen.queryByText(/正在获取板块成分股/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'重试成分股'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
  expect(screen.getByRole('button',{name:'查看承德露露 000848'})).toBeInTheDocument();
});
