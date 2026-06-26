import backend.config as config
from backend.notifications.seeoff import compute_seeoff_insights


def test_insights_rank_percentile_peak_trough():
    ins = compute_seeoff_insights(
        name="Hilbert Spaceship",
        final_pl_usd=1418.0,
        final_pl_pct=14.18,
        qpu_wins=7,
        total_solves=9,
        rank=3,
        total_agents=60,
        history_pcts=[0.0, 5.2, 18.1, 12.0, -2.3, 14.18],
    )
    assert ins.rank == 3
    assert ins.total_agents == 60
    assert ins.top_percent == 5  # ceil(3/60*100)
    assert ins.peak_pct == 18.1
    assert ins.trough_pct == -2.3
    assert ins.final_pl_pct == 14.18
    assert ins.jobs_solved == 9  # = total_solves
    assert ins.qpu_win_pct == 78  # round(7/9*100)


def test_top_percent_rounds_up_and_floors_at_1():
    # rank 1 of 60 → 1.67% → ceil 2; rank 1 of 200 → 0.5% → ceil 1 (never 0)
    def top(rank, total):
        return compute_seeoff_insights(
            name="a", final_pl_usd=0, final_pl_pct=0, qpu_wins=0, total_solves=0,
            rank=rank, total_agents=total, history_pcts=[],
        ).top_percent

    assert top(1, 60) == 2
    assert top(1, 200) == 1
    assert top(60, 60) == 100


def test_peak_trough_default_to_final_when_no_history():
    ins = compute_seeoff_insights(
        name="a", final_pl_usd=50, final_pl_pct=0.5, qpu_wins=0, total_solves=1,
        rank=10, total_agents=20, history_pcts=[],
    )
    assert ins.peak_pct == 0.5
    assert ins.trough_pct == 0.5


def test_recipients_and_render_end_to_end():
    # Full pipeline against a seeded in-memory store: only opted-in agents become recipients,
    # insights come out right, and the rendered email carries the personalised stats.
    from backend.api.schemas import AgentConfig, AgentUpdate, SliderValues
    from backend.notifications.email import render_seeoff_email
    from backend.notifications.seeoff import seeoff_recipients
    from backend.persistence.agents import AgentStore
    from backend.persistence.jobs import JobStore
    from backend.solvers.types import ProviderProvenance

    store = AgentStore()
    jobs = JobStore()
    sliders = SliderValues(rebalanceFrequency=50, riskPreference=70, maxPositionSize=50)
    opted = store.create(
        AgentConfig(name="Hilbert Spaceship", email="h@example.com", updatesOptIn=True, sliders=sliders),
        bankroll=10000.0, token_hash="t1",
    )
    store.create(  # opted OUT → must be excluded
        AgentConfig(name="No Mail", email="n@example.com", updatesOptIn=False, sliders=sliders),
        bankroll=10000.0, token_hash="t2",
    )
    store.apply_solve(opted.id, {"BTC": 1.0}, total=11418.0, provider_type="QPU")
    for total in (10500.0, 11810.0, 9800.0, 11418.0):  # peak +18.1%, trough -2.0%
        store.record_valuation_snapshot(
            opted.id, AgentUpdate(plUSD=total - 10000, plPct=(total - 10000) / 100, total=total)
        )
    for role in ("QPU", "QPU", "QPU", "CPU"):  # 3 of 4 won by the QPU → 75%
        jobs.record(opted.id, ProviderProvenance(
            provider="x", provider_role=role, q_hash="a" * 64,
            deadline_s=3.0, solve_time_s=0.1, feasible=True,
        ))

    recips = seeoff_recipients(store, jobs)
    assert [r.email for r in recips] == ["h@example.com"]  # only the opted-in one
    ins = recips[0].insights
    assert round(ins.final_pl_pct, 2) == 14.18
    assert ins.rank == 1 and ins.total_agents == 2  # ranked above the opted-out (idle) agent
    assert round(ins.peak_pct, 1) == 18.1
    assert round(ins.trough_pct, 1) == -2.0
    assert ins.jobs_solved == 4 and ins.qpu_win_pct == 75  # 3 of 4 solves won by the QPU

    email = render_seeoff_email(ins)
    assert "Hilbert Spaceship" in email.text
    assert "+14.18%" in email.text
    assert "75% won by the quantum computer" in email.text
    assert "see you in the quantum future" in email.text
    assert "Postquant Labs" in email.text
    assert "https://quip.network" in email.html  # linked in the signature
    assert "top 50%" in email.subject  # rank 1 of 2


def test_recurring_email_flag_off_suppresses_send(monkeypatch):
    # The RESULT_EMAILS_ENABLED kill-switch stops the throttled per-rebalance emails.
    from datetime import UTC, datetime

    from backend.notifications import dispatch

    sent: list[str] = []
    monkeypatch.setattr(dispatch, "send_portfolio_update", lambda **kw: sent.append(kw["to"]))
    monkeypatch.setattr(config, "RESULT_EMAILS_ENABLED", False)

    class _Rec:
        id = "a1"
        email = "x@example.com"
        updates_opt_in = True
        update_frequency = "daily"
        last_update_email_at = None
        name = "X"
        total = 1.0
        pl_usd = 1.0
        pl_pct = 1.0

    class _Store:
        def mark_update_email_sent(self, *a, **k):
            pass

    dispatch.maybe_send_update_email(_Rec(), now=datetime.now(UTC), store=_Store())
    assert sent == []  # suppressed by the flag
