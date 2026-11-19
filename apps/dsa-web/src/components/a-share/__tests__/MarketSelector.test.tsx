import {render,screen,fireEvent} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import MarketSelector from '../MarketSelector';
afterEach(()=>localStorage.clear());
it('offers all three markets with an explicit selected state',()=>{
 const change=vi.fn();render(<MarketSelector market="cn" onChange={change}/>);
 expect(screen.getByRole('button',{name:'A 股'})).toHaveAttribute('aria-pressed','true');
 fireEvent.click(screen.getByRole('button',{name:'美股'}));
 expect(change).toHaveBeenCalledWith('us');
 expect(screen.getByRole('button',{name:'港股'})).toBeEnabled();
});
