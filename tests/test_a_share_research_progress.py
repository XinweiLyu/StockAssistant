from src.services.a_share_research_progress import progress_view


def test_running_progress_uses_real_finished_roles_and_never_claims_complete():
    p=progress_view(dict(completed=5,expected=6,current='综合经理'), '2026-10-17T12:00:00+08:00')
    assert p['percent']==83
    assert p['elapsed_seconds'] is None and p['eta_seconds'] is None
    assert progress_view(dict(completed=6,expected=6,phase='saving'), '2026-10-17T12:00:00+08:00')['percent']==95


def test_eta_uses_observed_durations_and_current_role_elapsed_time():
    p=progress_view(dict(completed=1,expected=6,started_at='2026-10-17T10:00:00+08:00',
        current_started_at='2026-10-17T10:02:00+08:00',
        steps=[dict(status='ok',duration_seconds=120)]), '2026-10-17T10:02:30+08:00')
    assert p['elapsed_seconds']==150
    assert p['percent']==17
    assert p['eta_seconds']==[270,1170]
    assert p['eta_samples']==1


def test_missing_samples_and_overrun_do_not_invent_a_countdown():
    p=progress_view(dict(completed=0,expected=6,started_at='2026-10-17T10:00:00+08:00'), '2026-10-17T10:01:00+08:00')
    assert p['eta_seconds'] is None and p['elapsed_seconds']==60
    p=progress_view(dict(completed=5,expected=6,started_at='2026-10-17T10:00:00+08:00',current_started_at='2026-10-17T10:02:00+08:00',
        steps=[dict(status='ok',duration_seconds=120)]), '2026-10-17T10:07:00+08:00')
    assert p['eta_seconds'] is None and p['estimate_overrun'] is True
