import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getLeaderboard, getPublicValuationHistory, getRoutingStats, subscribeTvEvents } from '../../api';
import type { LeaderboardEntry, RoutingStats } from '../../api';
import StateA from './StateA';
import StateB from './StateB';
import StateC from './StateC';
import StateD from './StateD';

type StateName = 'A' | 'B' | 'C' | 'D';

// Production rotation: 12s leaderboard → 15s spotlight → 20s intro → repeat,
// stepping through ranks 1..10. A new-agent event interrupts for 10s.
const TIMINGS: Record<StateName, number> = { A: 12000, B: 15000, C: 20000, D: 10000 };

// Live data refresh cadence. Fast enough that the board visibly moves on screen.
const REFRESH_MS = 4000;

// Rolling per-agent total buffer for the spotlight sparkline (≈ last 60 points).
// Seeded from the public per-agent P&L history endpoint (token-free) the first
// time an agent is spotlighted, then extended by each live leaderboard poll — so
// the curve shows real movement immediately instead of only the points gathered
// since the TV happened to load.
const MAX_SPARK_POINTS = 60;

const EMPTY_ROUTING_STATS: RoutingStats = {
  total: 0,
  qpuWins: 0,
  cpuWins: 0,
  qpuPct: 0,
  cpuPct: 0,
  providers: [],
  recent: [],
};

export default function BoothTV() {
  const [params] = useSearchParams();
  const forced = params.get('state') as StateName | null;
  const spotlightAgentId = params.get('agent');

  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[] | null>(null);
  const [routingStats, setRoutingStats] = useState<RoutingStats>(EMPTY_ROUTING_STATS);
  const [state, setState] = useState<StateName>('A');
  const [spotIndex, setSpotIndex] = useState(0);
  const [interruptName, setInterruptName] = useState<string | null>(null);

  // Track the leaderboard length without re-running the rotation timer on each
  // ~4s data refresh — depending on `leaderboard` would reset the 12–20s timer
  // before it ever fires, freezing the rotation.
  const leaderboardLenRef = useRef(0);
  leaderboardLenRef.current = leaderboard?.length ?? 0;

  // Per-agent rolling P&L-total buffers, accumulated from each leaderboard poll.
  // Held in a ref so the curve survives State A/B remounts across the rotation
  // (a new agent's buffer starts empty and fills in as the board polls).
  const totalsByAgentRef = useRef<Map<string, number[]>>(new Map());

  // Agents whose stored P&L history we've already seeded into the buffer above
  // (one public fetch each). A state bump forces a re-render when a seed lands.
  const seededRef = useRef<Set<string>>(new Set());
  const [, bumpHist] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const board = await getLeaderboard();
        if (!cancelled) {
          const top = board.slice(0, 10);  // Top ten only — never overflow the TV
          setLeaderboard(top);
          // Append each agent's latest total to its rolling buffer, deduped so a
          // flat market doesn't pad the curve — this is what makes the spotlight
          // sparkline move as prices update.
          const buffers = totalsByAgentRef.current;
          for (const row of top) {
            const prev = buffers.get(row.agentId) ?? [];
            const last = prev[prev.length - 1];
            if (last === undefined || Math.abs(last - row.total) >= 0.005) {
              buffers.set(row.agentId, [...prev, row.total].slice(-MAX_SPARK_POINTS));
            }
          }
        }
      } catch {
        // Keep the last good leaderboard; the cold-start splash covers an empty board.
      }
      try {
        const stats = await getRoutingStats();
        if (!cancelled) setRoutingStats(stats);
      } catch {
        // Keep the last stats value; leaderboard freshness is more important.
      }
    };
    refresh();
    const interval = window.setInterval(refresh, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  // Real-time new-agent interrupt: the backend (and the mock) publish a
  // new-agent event on /tv/events when a first solve lands → flash State D.
  useEffect(() => {
    if (forced) return;            // a manually forced state owns the screen
    let timer: number | undefined;
    const unsubscribe = subscribeTvEvents(event => {
      if (event.type !== 'new-agent') return;
      setInterruptName(event.name);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setInterruptName(null), TIMINGS.D);
    });
    return () => {
      unsubscribe();
      window.clearTimeout(timer);
    };
  }, [forced]);

  useEffect(() => {
    if (forced || interruptName) return;   // don't rotate under a forced/interrupt state
    const t = setTimeout(() => {
      setState(prev => {
        if (prev === 'A') return 'B';
        if (prev === 'B') return 'C';
        if (prev === 'C') {
          setSpotIndex(i => {
            const n = leaderboardLenRef.current;
            return n ? (i + 1) % n : 0;
          });
          return 'A';
        }
        return 'A';
      });
    }, TIMINGS[state]);
    return () => clearTimeout(t);
  }, [state, forced, interruptName]);

  useEffect(() => {
    if (!leaderboard || !spotlightAgentId) return;
    const index = leaderboard.findIndex(row => row.agentId === spotlightAgentId);
    if (index >= 0) setSpotIndex(index);
  }, [leaderboard, spotlightAgentId]);

  // The agent currently in the spotlight (rotation index or forced ?agent=).
  const spotlightId =
    leaderboard && leaderboard.length
      ? (leaderboard[spotIndex % leaderboard.length] ?? leaderboard[0]).agentId
      : null;

  // Seed that agent's buffer with its REAL stored P&L history (public, token-free)
  // the first time it's spotlighted, so the sparkline shows true movement instead
  // of a flat line of points gathered since page load. Live polls extend it after.
  useEffect(() => {
    if (!spotlightId || seededRef.current.has(spotlightId)) return;
    seededRef.current.add(spotlightId);
    let cancelled = false;
    getPublicValuationHistory(spotlightId, MAX_SPARK_POINTS)
      .then(points => {
        if (cancelled || points.length < 2) return;
        totalsByAgentRef.current.set(
          spotlightId,
          points.map(point => point.total).slice(-MAX_SPARK_POINTS),
        );
        bumpHist(version => version + 1);
      })
      .catch(() => {
        seededRef.current.delete(spotlightId);  // allow a retry on the next pass
      });
    return () => {
      cancelled = true;
    };
  }, [spotlightId]);

  if (!leaderboard || leaderboard.length === 0) {
    return (
      <div style={{ width: '100vw', height: '100vh', background: '#0a0a10', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: '#4BE0FF', letterSpacing: '0.14em', textTransform: 'uppercase', fontSize: '1.1vw' }}>
          {leaderboard ? 'Awaiting the first agent…' : 'Connecting to the leaderboard…'}
        </div>
      </div>
    );
  }

  const active: StateName = forced ?? (interruptName ? 'D' : spotlightAgentId ? 'B' : state);
  const spotAgent = leaderboard[spotIndex % leaderboard.length] ?? leaderboard[0];
  const spotTotals = totalsByAgentRef.current.get(spotAgent.agentId) ?? [];
  // Re-key the stage on every view change so each state fades in cleanly.
  const fadeKey = `${active}-${active === 'B' ? spotIndex : ''}-${interruptName ?? ''}`;

  return (
    <div style={{
      width: '100vw', height: '100vh',
      background: '#0a0a10',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden',
    }}>
      <div style={{
        width: 'min(100vw, calc(100vh * 16 / 9))',
        height: 'min(100vh, calc(100vw * 9 / 16))',
      }}>
        <main className="tv-stage-fade" key={fadeKey} style={{ height: '100%' }}>
          {active === 'A' && <StateA leaderboard={leaderboard} routingStats={routingStats} phaseSeconds={TIMINGS.A / 1000} />}
          {active === 'B' && <StateB leaderboard={leaderboard} rankIndex={spotIndex} routingStats={routingStats} totals={spotTotals} phaseSeconds={TIMINGS.B / 1000} />}
          {active === 'C' && <StateC />}
          {active === 'D' && <StateD name={interruptName ?? undefined} />}
        </main>
      </div>
    </div>
  );
}
