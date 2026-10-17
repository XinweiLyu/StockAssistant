import { render,screen } from '@testing-library/react';
import { expect,it } from 'vitest';
import QuantOutlookPanel from '../QuantOutlookPanel';
import { outlookFixture } from './outlookFixture';
const controls={loading:false,horizon:20,minRewardRisk:2,onHorizon:()=>{},onMinRewardRisk:()=>{},onRetry:()=>{},showFan:true,onShowFan:()=>{},overlayMatched:true};
it('distinguishes price-error origins from the smaller interval-coverage validation sample',()=>{
  const data=outlookFixture();
  data.forecasts[1].validation={...data.forecasts[1].validation,samples:22,coverage_samples:14,coverage:1};
  render(<QuantOutlookPanel result={data} {...controls}/>);
  expect(screen.getByText(/滚动验证.*价格误差样本 22 个.*区间覆盖样本 14 个.*实测覆盖 100.0%/)).toBeInTheDocument();
});
it.each([undefined,null])('keeps unknown interval coverage denominator distinct from22 known error samples (%s)',coverageSamples=>{
  const data=outlookFixture();
  data.forecasts[1].validation={...data.forecasts[1].validation,samples:22,coverage_samples:coverageSamples};
  render(<QuantOutlookPanel result={data} {...controls}/>);
  expect(screen.getByText(/价格误差样本 22 个.*区间覆盖样本 资料不足/)).toBeInTheDocument();
});
it('shows insufficient coverage honestly even when error-validation samples are available',()=>{
  const data=outlookFixture();
  data.forecasts[1].validation={...data.forecasts[1].validation,samples:22,coverage_samples:0,coverage:null};
  render(<QuantOutlookPanel result={data} {...controls}/>);
  expect(screen.getByText(/价格误差样本 22 个.*区间覆盖样本 0 个.*实测覆盖 资料不足/)).toBeInTheDocument();
});
