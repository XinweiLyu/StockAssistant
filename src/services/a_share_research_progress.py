"""Read-only progress and cautious ETA from actual observed role durations."""
from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from statistics import median


def _elapsed(start, now):
    if not start:
        return None
    try:
        value=datetime.fromisoformat(str(start).replace('Z','+00:00'))
        value=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return max(0.,(now-value).total_seconds())
    except (ValueError,TypeError):
        return None


def progress_view(progress, now):
    if not progress:
        return None
    out=deepcopy(progress)
    instant=datetime.fromisoformat(str(now).replace('Z','+00:00'))
    instant=instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant
    expected=max(1,int(out.get('expected') or 6))
    completed=max(0,min(expected,int(out.get('completed') or 0)))
    percent=min(95,round(completed/expected*100))
    if out.get('phase')=='validating':percent=max(percent,90)
    if out.get('phase')=='saving':percent=95
    elapsed=_elapsed(out.get('started_at'),instant)
    durations=[s['duration_seconds'] for s in out.get('steps',[]) if s.get('status') in ('ok','failed','insufficient')
               and isinstance(s.get('duration_seconds'),(int,float)) and isfinite(s['duration_seconds']) and s['duration_seconds']>0]
    out.update(percent=percent,elapsed_seconds=round(elapsed) if elapsed is not None else None,
               eta_seconds=None,eta_samples=len(durations),estimate_overrun=False)
    if durations and completed<expected and out.get('phase','research')=='research':
        typical=median(durations)
        current=_elapsed(out.get('current_started_at'),instant) or 0
        if current>typical*2:
            out['estimate_overrun']=True
        else:
            pending=max(0,expected-completed-1)
            out['eta_seconds']=[round(max(0,typical*.5-current)+pending*typical*.5),
                                round(max(typical,typical*2-current)+pending*typical*2)]
    return out
