"""One-shot booth send-off: a personalised wrap-up email to every opted-in agent.

Computes per-agent insights from the data we kept intact — final P&L, leaderboard percentile
("top N%"), peak/trough over the booth, optimizations run, and the winning solver — then renders
and (optionally) sends a single farewell email. Default is a DRY RUN (preview only); pass
send=True to actually send. Idempotent via a local sent-id state file so a re-run can't
double-send.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from ..persistence.agents import AgentStore, get_agent_store
from ..persistence.jobs import JobStore, get_job_store
from .email import get_email_provider, render_seeoff_email

logger = logging.getLogger(__name__)

# Effectively "all" snapshots, so peak/trough reflect the whole booth, not just the last hour.
_HISTORY_LIMIT = 1_000_000


@dataclass(frozen=True)
class SeeoffInsights:
    name: str
    final_pl_usd: float
    final_pl_pct: float
    rank: int
    total_agents: int
    top_percent: int  # ceil(rank / total * 100), floored at 1 — "top N%"
    peak_pct: float
    trough_pct: float
    jobs_solved: int
    qpu_win_pct: int  # share of the agent's solves the quantum computer (QPU) won


def compute_seeoff_insights(
    *,
    name: str,
    final_pl_usd: float,
    final_pl_pct: float,
    qpu_wins: int,
    total_solves: int,
    rank: int,
    total_agents: int,
    history_pcts: list[float],
) -> SeeoffInsights:
    """Pure insight math: percentile (rounded up, floored at 1), peak/trough P&L% over the booth
    (incl. the final mark, so a flat/empty history still yields sane peak == trough), and the
    share of the agent's solves the quantum computer won."""
    pcts = list(history_pcts) + [final_pl_pct]
    top_percent = min(100, max(1, math.ceil(rank / total_agents * 100))) if total_agents > 0 else 100
    qpu_win_pct = round(qpu_wins / total_solves * 100) if total_solves > 0 else 0
    return SeeoffInsights(
        name=name,
        final_pl_usd=final_pl_usd,
        final_pl_pct=final_pl_pct,
        rank=rank,
        total_agents=total_agents,
        top_percent=top_percent,
        peak_pct=max(pcts),
        trough_pct=min(pcts),
        jobs_solved=total_solves,
        qpu_win_pct=qpu_win_pct,
    )


@dataclass(frozen=True)
class Recipient:
    agent_id: str
    email: str
    insights: SeeoffInsights


def seeoff_recipients(
    store: AgentStore | None = None, jobs: JobStore | None = None
) -> list[Recipient]:
    """Every opted-in agent that has an email, each with computed insights. Rank/percentile rank
    the agent by its true total against ALL agents (including admin-hidden ones — they still
    competed and deserve an honest standing, e.g. a hidden agent that placed #3 overall). The QPU
    win-rate is tallied from each agent's winning solves in the job log."""
    store = store or get_agent_store()
    jobs = jobs or get_job_store()
    qpu_wins: dict[str, int] = {}
    total_solves: dict[str, int] = {}
    for job in jobs.all():
        total_solves[job.agent_id] = total_solves.get(job.agent_id, 0) + 1
        if job.provider_role == "QPU":
            qpu_wins[job.agent_id] = qpu_wins.get(job.agent_id, 0) + 1
    ranked = sorted(store.all(), key=lambda r: (-r.total, r.id))
    total = len(ranked)
    rank_by_id = {record.id: index + 1 for index, record in enumerate(ranked)}
    out: list[Recipient] = []
    for record in ranked:
        if record.updates_opt_in is not True or not record.email:
            continue
        history = store.valuation_history(record.id, limit=_HISTORY_LIMIT)
        out.append(
            Recipient(
                agent_id=record.id,
                email=record.email,
                insights=compute_seeoff_insights(
                    name=record.name,
                    final_pl_usd=record.pl_usd,
                    final_pl_pct=record.pl_pct,
                    qpu_wins=qpu_wins.get(record.id, 0),
                    total_solves=total_solves.get(record.id, record.jobs_solved),
                    rank=rank_by_id.get(record.id, total + 1),
                    total_agents=max(total, 1),
                    history_pcts=[p.pl_pct for p in history],
                ),
            )
        )
    return out


def _load_sent(state_path: Path) -> set[str]:
    try:
        return set(json.loads(state_path.read_text()))
    except Exception:
        return set()


@dataclass
class SeeoffSummary:
    recipients: int
    already_sent: int
    sent: int
    failed: int


def send_seeoff(
    store: AgentStore | None = None,
    *,
    send: bool = False,
    state_path: Path | None = None,
    limit: int | None = None,
) -> SeeoffSummary:
    """Render and (when send=True) deliver the send-off to every opted-in agent. Dry run by
    default — it computes + renders everything but sends nothing. Already-sent agents (per the
    state file) are skipped on a real send so a re-run never double-sends."""
    state_path = state_path or Path("seeoff_sent.json")
    recipients = seeoff_recipients(store)
    if limit is not None:
        recipients = recipients[:limit]
    already = _load_sent(state_path) if send else set()
    summary = SeeoffSummary(recipients=len(recipients), already_sent=0, sent=0, failed=0)
    provider = get_email_provider()
    for recipient in recipients:
        if recipient.agent_id in already:
            summary.already_sent += 1
            continue
        email = render_seeoff_email(recipient.insights)
        if not send:
            continue
        try:
            provider.send(to=recipient.email, subject=email.subject, html=email.html, text=email.text)
            already.add(recipient.agent_id)
            summary.sent += 1
            state_path.write_text(json.dumps(sorted(already)))  # persist after each send
        except Exception:
            summary.failed += 1
            logger.warning("send-off email failed agent_id=%s", recipient.agent_id, exc_info=True)
    return summary
