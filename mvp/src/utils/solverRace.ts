import type { RoutingResult, SolverResult, SolverResultsFrame } from '../api';

export type SolverRaceRow = SolverResult & {
  label: string;
  detail: string;
  timeLabel: string;
  barPct: number;
  isWinner: boolean;
};

export type SolverRaceComparison = {
  value: string;
  label: string;
  summary: string;
};

const STATUS_ORDER: Record<SolverResult['status'], number> = {
  winner: 0,
  feasible: 1,
  infeasible: 2,
  pending: 3,
  skipped: 4,
  failed: 5,
  timeout: 6,
};

// Late solver results replace the rows of the race they belong to; a frame for an older
// job (the agent re-solved meanwhile) leaves the shown race alone.
export function applySolverResults(
  result: RoutingResult | null,
  frame: SolverResultsFrame,
): RoutingResult | null {
  if (!result?.jobId || result.jobId !== frame.jobId) return result;
  return { ...result, solverResults: frame.solverResults };
}

export function solverRaceRows(result: RoutingResult | null): SolverRaceRow[] {
  if (!result) return [];
  const rows = result.solverResults?.length ? result.solverResults : [winnerOnlyRow(result)];
  const sorted = [...rows].sort((a, b) => {
    const statusDelta = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    if (statusDelta !== 0) return statusDelta;
    return displaySeconds(a) - displaySeconds(b);
  });
  // Bars represent solve time, so only solvers that produced a timed, usable
  // result get one; failed/timeout/infeasible rows render empty rather than a
  // misleading "fastest-looking" sliver.
  const solvedSeconds = sorted.filter(solved).map(row => row.solveTime as number);
  const maxSeconds = Math.max(...solvedSeconds, 0.01);

  return sorted.map(row => ({
    ...row,
    label: `${row.provider} · ${row.providerType}`,
    detail: detailFor(row),
    timeLabel: timeLabelFor(row),
    barPct: solved(row)
      ? Math.max(4, Math.min(100, ((row.solveTime as number) / maxSeconds) * 100))
      : 0,
    isWinner: row.status === 'winner',
  }));
}

function solved(row: SolverResult): boolean {
  return (
    row.solveTime != null &&
    row.status !== 'failed' &&
    row.status !== 'timeout' &&
    row.status !== 'infeasible'
  );
}

export function solverRaceComparison(result: RoutingResult | null): SolverRaceComparison {
  const rows = solverRaceRows(result);
  const winner = rows.find(row => row.isWinner);
  const opponent = raceRunnerUp(rows);
  if (!winner || !opponent || winner.solveTime == null || opponent.solveTime == null) {
    return {
      value: '—',
      label: 'Solver Margin',
      summary: winner ? `${winner.label}` : 'Solver comparison pending',
    };
  }

  // The backend classifies the outcome with the authoritative objective + time tolerances. The race
  // is scored on PORTFOLIO QUALITY (best objective): the winner can be the best portfolio yet slower.
  //   tie     → objective AND speed within tolerance: a genuine tie, NOT a noise-level "X% faster".
  //   speed   → objective tie, winner materially faster: a real speed win.
  //   quality → winner's portfolio is materially better (time shown alongside).
  const fasterPct = ((opponent.solveTime - winner.solveTime) / opponent.solveTime) * 100;
  const outcome = result?.outcome ?? (fasterPct >= 1 ? 'speed' : 'quality');
  if (outcome === 'tie') {
    return {
      value: 'Tie',
      label: `${winner.providerType} = ${opponent.providerType}`,
      summary: `Tie · both found the best portfolio`,
    };
  }
  if (outcome === 'speed') {
    const rounded = Math.max(1, Math.round(fasterPct));
    return {
      value: `${rounded}%`,
      label: `Faster than ${opponent.providerType}`,
      summary: `${rounded}% faster than ${opponent.providerType}`,
    };
  }
  return {
    value: 'Best',
    label: `Portfolio vs ${opponent.providerType}`,
    summary: `Best portfolio vs ${opponent.providerType} · ${winner.providerType} ${winner.timeLabel}`,
  };
}

// The solver the winner is compared against, picked as the backend picks it for `outcome`
// and the TV: the feasible race solver with the lowest objective. A Quip order runs outside
// the race, so it is never one. Equal objectives go to the faster solver, as in the backend.
// Rows without objectives (demo data) fall back to the fastest feasible solver.
function raceRunnerUp(rows: SolverRaceRow[]): SolverRaceRow | undefined {
  const candidates = rows.filter(
    row => !row.isWinner && row.feasible && row.solveTime != null && row.providerType !== 'NETWORK',
  );
  const scored = candidates.filter(row => row.objective != null);
  if (scored.length === 0) return candidates[0];
  return scored.reduce((best, row) =>
    row.objective! < best.objective! ||
    (row.objective === best.objective && row.solveTime! < best.solveTime!)
      ? row
      : best,
  );
}

// A result without per-solver rows still names its winner.
function winnerOnlyRow(result: RoutingResult): SolverResult {
  return {
    provider: result.provider,
    providerType: result.providerType,
    status: 'winner',
    feasible: true,
    solveTime: result.solveTime,
    raceTime: result.solveTime,
  };
}

function displaySeconds(row: SolverResult): number {
  return row.solveTime ?? 0.01;
}

function timeLabelFor(row: SolverResult): string {
  if (row.status === 'pending') return 'on chain…';
  if (row.status === 'skipped') return 'skipped';
  if (row.status === 'timeout') return 'timeout';
  if (row.status === 'failed') return 'failed';
  const seconds = row.solveTime;
  return seconds == null ? '—' : `${seconds.toFixed(2)}s`;
}

function detailFor(row: SolverResult): string {
  return [statusDetail(row), orderDetail(row)].filter(Boolean).join(' · ');
}

function statusDetail(row: SolverResult): string {
  if (row.status === 'winner') return 'winner';
  // 'feasible' is internal jargon — a valid runner-up needs no extra label.
  if (row.status === 'feasible') return '';
  return row.status; // infeasible / failed / timeout stay informative
}

// A Quip order is on chain under its order ID once proposed; show it so it can be looked up.
export function orderDetail(row: SolverResult): string {
  return row.orderId ? `order\u00a0${row.orderId}` : '';  // never split from its number
}
