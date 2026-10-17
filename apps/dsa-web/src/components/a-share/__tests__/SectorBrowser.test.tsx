import { render,screen,fireEvent } from '@testing-library/react';
import { vi,it,expect } from 'vitest';
import SectorHeatmap from '../SectorHeatmap';
import { normalizedComparison } from '../priceChartData';
const sector={sector_id:'em:industry:BK1',code:'BK1',name:'同名行业',kind:'industry' as const,classification:'eastmoney-industry',source:'fixture',fetched_at:'2026-10-09',change:null};
it('unknown change is grey, not zero, and sector selection uses identity',()=>{
  const select=vi.fn();render(<SectorHeatmap items={[sector]} onSelect={select}/>);
  fireEvent.click(screen.getByRole('button',{name:/资料不足/}));expect(select).toHaveBeenCalledWith(sector);expect(screen.queryByText('0.00%')).not.toBeInTheDocument();
});
it('comparison uses only common dates and no interpolation',()=>{
  const b=(date:string,close:number)=>({date,open:close,high:close,low:close,close});
  const result=normalizedComparison([{name:'行业',items:[b('2026-10-01',9),b('2026-10-02',10),b('2026-10-03',12)]},{name:'基准',items:[b('2026-10-02',20),b('2026-10-03',21)]}]);
  expect(result).toEqual([{date:'2026-10-02',行业:100,基准:100},{date:'2026-10-03',行业:120,基准:105}]);
});
