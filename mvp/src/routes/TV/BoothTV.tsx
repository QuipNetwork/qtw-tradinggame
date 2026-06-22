import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getLeaderboard, getRoutingStats, subscribeTvEvents } from '../../api';
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

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const board = await getLeaderboard();
        if (!cancelled) setLeaderboard(board.slice(0, 10));  // Top ten only — never overflow the TV
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
            const n = leaderboard?.length ?? 0;
            return n ? (i + 1) % n : 0;
          });
          return 'A';
        }
        return 'A';
      });
    }, TIMINGS[state]);
    return () => clearTimeout(t);
  }, [state, forced, interruptName, leaderboard]);

  useEffect(() => {
    if (!leaderboard || !spotlightAgentId) return;
    const index = leaderboard.findIndex(row => row.agentId === spotlightAgentId);
    if (index >= 0) setSpotIndex(index);
  }, [leaderboard, spotlightAgentId]);

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
        <div className="tv-stage-fade" key={fadeKey} style={{ height: '100%' }}>
          {active === 'A' && <StateA leaderboard={leaderboard} routingStats={routingStats} phaseSeconds={TIMINGS.A / 1000} />}
          {active === 'B' && <StateB leaderboard={leaderboard} rankIndex={spotIndex} routingStats={routingStats} phaseSeconds={TIMINGS.B / 1000} />}
          {active === 'C' && <StateC />}
          {active === 'D' && <StateD name={interruptName ?? undefined} />}
        </div>
      </div>
    </div>
  );
}
