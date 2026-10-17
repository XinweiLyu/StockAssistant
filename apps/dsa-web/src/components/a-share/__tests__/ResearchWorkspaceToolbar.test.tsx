import {render,screen,fireEvent} from '@testing-library/react';
import {it,expect,vi} from 'vitest';
import ResearchWorkspaceToolbar from '../ResearchWorkspaceToolbar';
import {integratedFixture} from './integratedFixture';

it('keeps forecast intervals next to the chart and starts only the integrated workflow',()=>{
 const generate=vi.fn(),s=integratedFixture();
 render(<ResearchWorkspaceToolbar result={s} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={generate} overlayMatched/>);
 expect(screen.getByRole('region',{name:'未来情景预测区间'})).toHaveTextContent('¥21.00');
 expect(screen.getAllByRole('button',{name:'生成综合研究与价位'})).toHaveLength(1);
 fireEvent.click(screen.getByRole('button',{name:'生成综合研究与价位'}));
 expect(generate).toHaveBeenCalledOnce();
});

it('preserves stale intervals with a visible historical label and the reason for no chart overlay',()=>{
 const s=integratedFixture();s.report!.stale=true;s.status='running';s.progress={completed:5,expected:6,current:'综合经理',message:'正在研究',percent:83};
 render(<ResearchWorkspaceToolbar result={s} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}} overlayMatched={false}/>);
 expect(screen.getByRole('region',{name:'未来情景预测区间'})).toHaveTextContent('历史研究');
 expect(screen.getByText(/暂不叠加/)).toBeInTheDocument();
 expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow','83');
 expect(screen.getByText(/暂无法估算/)).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'生成综合研究与价位'})).toBeDisabled();
});

it('shows a bounded ETA from measured roles and reports completed cached research at 100 percent',()=>{
 const s=integratedFixture();s.status='running';s.progress={completed:1,expected:6,current:'业绩与估值',message:'研究中',percent:17,elapsed_seconds:150,eta_seconds:[270,1170],eta_samples:1};
 const {rerender}=render(<ResearchWorkspaceToolbar result={s} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
 expect(screen.getByText(/5–20分钟/)).toBeInTheDocument();
 expect(screen.getByText(/已用时.*2分30秒/)).toBeInTheDocument();
 rerender(<ResearchWorkspaceToolbar result={integratedFixture()} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
 expect(screen.getByText(/已完成.*100%/)).toBeInTheDocument();
});


it('explains rejected horizon intervals while preserving the accepted ranges',()=>{
 const s=integratedFixture();s.report!.rejections=[{kind:'forecast',horizon:20,reason:'缺财务依据'}];
 render(<ResearchWorkspaceToolbar result={s} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
 expect(screen.getByRole('region',{name:'未来情景预测区间'})).toHaveTextContent('缺财务依据');
 expect(screen.getByRole('region',{name:'未来情景预测区间'})).toHaveTextContent('¥21.00');
 expect(screen.getAllByText('未提供')).toHaveLength(2);
});


it('distinguishes a stopped research run from a successfully generated price forecast',()=>{
 const s=integratedFixture();s.report!.status='partial';s.report!.forecasts=[];s.report!.plans=[];
 s.report!.roles=[{role:'technical_analyst',label:'价格与流动性',status:'failed',claims:[],message:'模型请求未完成：CalledProcessError'},{role:'risk_reviewer',label:'风险复核',status:'failed',claims:[]},{role:'research_manager',label:'综合经理',status:'failed',claims:[]}];
 render(<ResearchWorkspaceToolbar result={s} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
 expect(screen.getByText(/价位生成失败/)).toBeInTheDocument();
 expect(screen.queryByText(/部分结果有效.*100%/)).not.toBeInTheDocument();
 expect(screen.getByRole('alert')).toHaveTextContent('价格与流动性、风险复核、综合经理');
 expect(screen.getByRole('alert')).toHaveTextContent('未生成');
 expect(screen.getByRole('button',{name:'生成综合研究与价位'})).toBeEnabled();
});

it('explains an intentionally withheld forecast without calling it a model failure',()=>{
 const s=integratedFixture();s.report!.status='partial';s.report!.forecasts=[];s.report!.plans=[];
 render(<ResearchWorkspaceToolbar result={s} horizon={20} onHorizon={()=>{}} onPrepare={()=>{}} onGenerate={()=>{}}/>);
 expect(screen.getByText(/未发布预测价位/)).toBeInTheDocument();
 expect(screen.queryByText(/价位生成失败/)).not.toBeInTheDocument();
 expect(screen.getByRole('region',{name:'未来情景预测区间'})).toHaveTextContent('没有通过校验');
});
