import type { IntegratedReport } from '../../types/aShareMarket';

// Processing every role does not imply that a valid price forecast was produced.
export function integratedResearchStatus(report:IntegratedReport|null|undefined,horizon:number) {
  const failedRoles=(report?.roles||[]).filter(r=>r.status==='failed');
  const valid=(n:unknown)=>typeof n==='number'&&Number.isFinite(n)&&n>0;
  const forecasts=(report?.forecasts||[]).filter(f=>valid(f.low)&&valid(f.high)&&f.low<=f.high);
  const hasPrices=forecasts.length>0||(report?.plans||[]).some(p=>[p.entry_low,p.entry_high,p.stop_reference,...p.targets].some(valid));
  const priceFailed=!!report&&!hasPrices&&(failedRoles.length>0||report.status==='failed');
  const labels=failedRoles.map(r=>r.label||r.role).join('、');
  const missingReason=!report||forecasts.some(f=>f.horizon_sessions===horizon)?undefined:
    failedRoles.length?`${horizon}日预测区间未生成；模型调用失败环节：${labels}。已完成的观点与资料仍保留，该期限没有区间可叠加到K线。`:
    report.status==='failed'?'综合研究失败，未生成预测区间；已有资料仍保留。':
    `${horizon}日没有通过校验的预测区间，该期限无区间线可绘制。请查看资料缺口与拒收原因。`;
  const title=priceFailed?'价位生成失败':!hasPrices?'已结束，未发布预测价位':report?.status==='partial'?'已结束，部分结果有效':'已完成';
  return {failedRoles,hasPrices,priceFailed,missingReason,title};
}
