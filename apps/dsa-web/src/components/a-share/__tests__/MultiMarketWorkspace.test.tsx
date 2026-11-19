import {useState} from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import InvestmentWorkspace from '../InvestmentWorkspace';
import apiClient from '../../../api';
import type {AssistantBoard} from '../../../types/aShare';
vi.mock('../../../api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn(),delete:vi.fn()}}));
vi.mock('../StockDetail',()=>({default:({code}:{code:string})=><section aria-label="当前详情">{code}</section>}));
const board={settings:{mode:'free',watchlist:[],research_enabled:true},report:null,research:[],events:[]} as unknown as AssistantBoard;
beforeEach(()=>{
 localStorage.clear();vi.clearAllMocks();
 vi.mocked(apiClient.get).mockImplementation(async url=>{
  if(url?.endsWith('/jobs'))return {data:{counts:{},paused:false,coverage:{catalog_total:1}}};
  if(url?.endsWith('/watchlist'))return {data:{codes:[]}};
  if(url?.endsWith('/sectors'))return {data:{items:[]}};
  const us=url?.includes('/market-workspace/us');
  return {data:{items:[{code:us?'us:AAPL':'000807',name:us?'Apple':'云铝股份',quote:null}],total:1,page:1,page_size:50}};
 });
});
afterEach(()=>localStorage.clear());
function Workspace(){const [code,setCode]=useState('000807');return <InvestmentWorkspace board={board} selectedCode={code} onSelectStock={setCode} onWatchlist={()=>{}} onResearch={()=>{}}/>;}
it('switches the actual catalog and detail, then restores A-share selection without a model call',async()=>{
 render(<Workspace/>);
 expect(screen.getByLabelText('当前详情')).toHaveTextContent('000807');
 fireEvent.click(screen.getByRole('button',{name:'美股'}));
 const apple=await screen.findByRole('button',{name:'Apple us:AAPL'});
 fireEvent.click(apple);
 expect(screen.getByLabelText('当前详情')).toHaveTextContent('us:AAPL');
 await waitFor(()=>expect(apiClient.get).toHaveBeenCalledWith('/api/v1/market-workspace/us/stocks',expect.anything()));
 fireEvent.click(screen.getByRole('button',{name:'A 股'}));
 expect(screen.getByLabelText('当前详情')).toHaveTextContent('000807');
 expect(apiClient.post).not.toHaveBeenCalled();
});

it('restores each market search filter independently',async()=>{
 render(<Workspace/>);
 fireEvent.change(screen.getByPlaceholderText('代码或股票名称'),{target:{value:'云铝'}});
 fireEvent.click(screen.getByRole('button',{name:'美股'}));
 expect(screen.getByPlaceholderText('代码或股票名称')).toHaveValue('');
 fireEvent.change(screen.getByPlaceholderText('代码或股票名称'),{target:{value:'Apple'}});
 fireEvent.click(screen.getByRole('button',{name:'A 股'}));
 expect(screen.getByPlaceholderText('代码或股票名称')).toHaveValue('云铝');
 fireEvent.click(screen.getByRole('button',{name:'美股'}));
 expect(screen.getByPlaceholderText('代码或股票名称')).toHaveValue('Apple');
});
