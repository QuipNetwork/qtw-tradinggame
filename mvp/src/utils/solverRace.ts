import type { RoutingResult, SolverResult } from '../api';

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
  failed: 3,
  timeout: 4,
};

export function solverRaceRows(result: RoutingResult | null): SolverRaceRow[] {
  const rows = result?.solverResults?.length ? result.solverResults : fallbackRows(result);
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
  const opponent = rows.find(row => !row.isWinner && row.feasible && row.solveTime != null);
  if (!winner || !opponent || winner.solveTime == null || opponent.solveTime == null) {
    return {
      value: '—',
      label: 'Solver Margin',
      summary: winner ? `${winner.label}` : 'Solver comparison pending',
    };
  }

  const fasterPct = Math.max(
    0,
    ((opponent.solveTime - winner.solveTime) / opponent.solveTime) * 100,
  );
  const rounded = Math.round(fasterPct);
  return {
    value: `${rounded}%`,
    label: `Faster than ${opponent.providerType}`,
    summary: `${rounded}% faster than ${opponent.providerType}`,
  };
}

function fallbackRows(result: RoutingResult | null): SolverResult[] {
  const solveTime = result?.solveTime ?? 0.42;
  return [
    {
      provider: result?.provider ?? 'D-Wave Advantage',
      providerType: result?.providerType ?? 'QPU',
      status: 'winner',
      feasible: true,
      solveTime,
      raceTime: solveTime,
    },
  ];
}

function displaySeconds(row: SolverResult): number {
  return row.solveTime ?? 0.01;
}

function timeLabelFor(row: SolverResult): string {
  if (row.status === 'timeout') return 'timeout';
  if (row.status === 'failed') return 'failed';
  const seconds = row.solveTime;
  return seconds == null ? '—' : `${seconds.toFixed(2)}s`;
}

function detailFor(row: SolverResult): string {
  if (row.status === 'winner') return 'winner';
  // 'feasible' is internal jargon — a valid runner-up needs no extra label.
  if (row.status === 'feasible') return '';
  return row.status; // infeasible / failed / timeout stay informative
}
