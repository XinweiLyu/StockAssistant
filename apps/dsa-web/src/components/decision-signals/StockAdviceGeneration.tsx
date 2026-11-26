import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { analysisApi, DuplicateTaskError } from '../../api/analysis';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { TaskStatus } from '../../types/analysis';
import { areStockCodesEquivalent } from '../../utils/stockCode';
import { ApiErrorAlert } from '../common';

type GenerationState =
  | { phase: 'checking' | 'idle' | 'submitting' | 'cancelled' }
  | { phase: 'submissionError'; error: ParsedApiError }
  | { phase: 'tracking'; id: string; status: TaskStatus['status']; progress?: number; reconnecting?: boolean }
  | { phase: 'refreshing'; id: string }
  | { phase: 'complete'; refreshed: boolean }
  | { phase: 'trackingError' | 'analysisFailed' };

interface StockAdviceGenerationProps {
  code: string;
  name: string;
  onReportSaved: () => Promise<boolean>;
}

const ACTIVE_STATUSES: TaskStatus['status'][] = ['pending', 'processing', 'cancel_requested'];
const POLL_INTERVAL = 2_000;
const RETRY_INTERVAL = 5_000;

export function StockAdviceGeneration({ code, name, onReportSaved }: StockAdviceGenerationProps) {
  const { t } = useUiLanguage();
  const [state, setState] = useState<GenerationState>({ phase: 'checking' });
  const submitting = useRef(false);
  const refreshResults = useEffectEvent(onReportSaved);
  const taskId = state.phase === 'tracking' || state.phase === 'refreshing' ? state.id : null;

  useEffect(() => {
    let disposed = false;
    void analysisApi.getTasks({ status: ACTIVE_STATUSES.join(','), limit: 100 }).then(({ tasks }) => {
      if (disposed) return;
      const existing = tasks.find(task => (
        task.assetType !== 'index'
        && ACTIVE_STATUSES.includes(task.status)
        && areStockCodesEquivalent(task.stockCode, code)
      ));
      setState(existing
        ? { phase: 'tracking', id: existing.taskId, status: existing.status, progress: existing.progress }
        : { phase: 'idle' });
    }, () => {
      if (!disposed) setState({ phase: 'idle' });
    });
    return () => { disposed = true; };
  }, [code]);

  useEffect(() => {
    if (!taskId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      let task: TaskStatus;
      try {
        task = await analysisApi.getStatus(taskId);
      } catch (error) {
        if (disposed) return;
        if (getParsedApiError(error).status === 404) {
          setState({ phase: 'trackingError' });
          return;
        }
        setState(current => current.phase === 'tracking' ? { ...current, reconnecting: true } : current);
        timer = setTimeout(poll, RETRY_INTERVAL);
        return;
      }
      if (disposed) return;
      if (ACTIVE_STATUSES.includes(task.status)) {
        setState({ phase: 'tracking', id: taskId, status: task.status, progress: task.progress });
        timer = setTimeout(poll, POLL_INTERVAL);
      } else if (task.status === 'completed') {
        setState({ phase: 'refreshing', id: taskId });
        const refreshed = await refreshResults();
        if (!disposed) setState({ phase: 'complete', refreshed });
      } else {
        setState({ phase: task.status === 'cancelled' ? 'cancelled' : 'analysisFailed' });
      }
    };
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [taskId]);

  const generate = async () => {
    if (submitting.current) return;
    submitting.current = true;
    setState({ phase: 'submitting' });
    try {
      const accepted = await analysisApi.analyzeAsync({
        stockCode: code,
        stockName: name,
        reportType: 'detailed',
        selectionSource: 'autocomplete',
        notify: false,
      });
      const task = 'taskId' in accepted ? accepted : accepted.accepted[0];
      if (!task?.taskId) {
        setState({ phase: 'trackingError' });
        return;
      }
      setState({ phase: 'tracking', id: task.taskId, status: task.status });
    } catch (error) {
      if (error instanceof DuplicateTaskError && error.existingTaskId) {
        setState({ phase: 'tracking', id: error.existingTaskId, status: 'pending' });
      } else {
        setState({ phase: 'submissionError', error: getParsedApiError(error) });
      }
    } finally {
      submitting.current = false;
    }
  };

  const busy = state.phase === 'checking' || state.phase === 'submitting' || taskId !== null;
  const progress = state.phase === 'tracking' && Number.isFinite(state.progress)
    ? Math.min(100, Math.max(0, Math.round(state.progress ?? 0)))
    : undefined;
  const status = (() => {
    switch (state.phase) {
      case 'checking': return t('decisionSignals.generationChecking');
      case 'submitting': return t('decisionSignals.generationSubmitting');
      case 'tracking':
        if (state.status === 'pending') return t('decisionSignals.generationQueued');
        if (state.status === 'cancel_requested') return t('decisionSignals.generationCancelling');
        return progress === undefined
          ? t('decisionSignals.generationRunning')
          : t('decisionSignals.generationProgress', { progress });
      case 'refreshing': return t('decisionSignals.generationRefreshing');
      case 'complete': return t(state.refreshed ? 'decisionSignals.generationComplete' : 'decisionSignals.generationReadFailed');
      case 'cancelled': return t('decisionSignals.generationCancelled');
      default: return null;
    }
  })();

  return (
    <div className="space-y-2 rounded-xl border border-border/70 bg-elevated/30 p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <button type="button" className="btn-primary" disabled={busy} onClick={() => void generate()}>
          {t('decisionSignals.generationStart')}
        </button>
        {!busy && !status && <p className="text-xs text-secondary-text">{t('decisionSignals.generationUsesModel')}</p>}
      </div>
      {status && <p role="status" className="font-medium text-foreground">{status}</p>}
      {state.phase === 'tracking' && progress !== undefined && (
        <progress aria-label={t('decisionSignals.generationRunning')} className="block h-2 w-full accent-primary" value={progress} max={100} />
      )}
      {state.phase === 'tracking' && state.reconnecting && (
        <p className="text-sm text-secondary-text">{t('decisionSignals.generationReconnecting')}</p>
      )}
      {state.phase === 'submissionError' && <ApiErrorAlert error={state.error} />}
      {(state.phase === 'trackingError' || state.phase === 'analysisFailed') && (
        <p role="alert" className="text-sm text-danger">
          {t(state.phase === 'trackingError' ? 'decisionSignals.generationTaskMissing' : 'decisionSignals.generationFailed')}
        </p>
      )}
    </div>
  );
}
