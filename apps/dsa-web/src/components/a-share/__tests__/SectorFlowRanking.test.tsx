import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import SectorBrowser from '../SectorBrowser';
import {aShareMarketApi} from '../../../api/aShareMarket';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{sectors:vi.fn(),fundFlowRank:vi.fn()}}));
it('sorts main net amounts by exact board ID, leaves missing unknown and preserves navigation',async()=>{
 const board=(code:string,name:string)=>({sector_id:'em:industry:'+code,code,name,kind:'industry' as const,classification:'eastmoney-industry',change:0,source:'fixture',fetched_at:'now'});
 const a=board('BK0478','有色金属'),b=board('BK0438','食品饮料');
 vi.mocked(aShareMarketApi.sectors).mockResolvedValue({items:[a,b],classification:'eastmoney-industry',period:0,demo:false});
 vi.mocked(aShareMarketApi.fundFlowRank).mockResolvedValue({items:[{sector_id:b.sector_id,name:b.name,observed_at:'2026-11-17T02:00:00Z',values:{main:1e8,super:null,large:null,medium:null,small:null},ratios:{main:.02}}],health:{status:'ready'},source:'eastmoney',unit:'CNY',limitations:[]});
 const select=vi.fn();render(<SectorBrowser onSelectSector={select}/>);await screen.findByText('有色金属');fireEvent.change(screen.getByLabelText('板块排序指标'),{target:{value:'main_net'}});
 await waitFor(()=>expect(aShareMarketApi.fundFlowRank).toHaveBeenCalledWith('industry',expect.any(AbortSignal)));
 const bButton=await screen.findByRole('button',{name:'食品饮料 +1.00亿'});fireEvent.click(bButton);expect(select).toHaveBeenCalledWith(b);
 expect(screen.getByRole('button',{name:'有色金属 资料不足'})).toBeInTheDocument();expect(screen.getByLabelText('板块区间')).toBeDisabled();
});
