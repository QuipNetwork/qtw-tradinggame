import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getLeaderboard, getRoutingStats } from '../../api';
import type { LeaderboardEntry, RoutingStats } from '../../api';
import StateA from './StateA';
import StateB from './StateB';
import StateC from './StateC';
import StateD from './StateD';

type StateName = 'A' | 'B' | 'C' | 'D';

// Production rotation: 12s leaderboard → 15s spotlight → 20s intro → repeat,
// stepping through ranks 1..10. State D interrupts for 10s on new agent.
const TIMINGS: Record<StateName, number> = { A: 12000, B: 15000, C: 20000, D: 10000 };

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

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const board = await getLeaderboard();
      if (!cancelled) setLeaderboard(board.slice(0, 10));  // Top ten only — never overflow the TV
      try {
        const stats = await getRoutingStats();
        if (!cancelled) setRoutingStats(stats);
      } catch {
        // Keep the last stats value; leaderboard freshness is more important.
      }
    };
    refresh();
    const interval = window.setInterval(refresh, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (forced) return;
    const t = setTimeout(() => {
      setState(prev => {
        if (prev === 'A') return 'B';
        if (prev === 'B') return 'C';
        if (prev === 'C') {
          setSpotIndex(i => (i + 1) % (leaderboard?.length ?? 10));
          return 'A';
        }
        return 'A';
      });
    }, TIMINGS[state]);
    return () => clearTimeout(t);
  }, [state, forced, leaderboard]);

  useEffect(() => {
    if (!leaderboard || !spotlightAgentId) return;
    const index = leaderboard.findIndex(row => row.agentId === spotlightAgentId);
    if (index >= 0) setSpotIndex(index);
  }, [leaderboard, spotlightAgentId]);

  if (!leaderboard) {
    return <div style={{ width: '100vw', height: '100vh', background: '#0a0a10' }} />;
  }

  const active = forced ?? (spotlightAgentId ? 'B' : state);

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
        {active === 'A' && <StateA leaderboard={leaderboard} routingStats={routingStats} />}
        {active === 'B' && <StateB leaderboard={leaderboard} rankIndex={spotIndex} routingStats={routingStats} />}
        {active === 'C' && <StateC />}
        {active === 'D' && <StateD />}
      </div>
    </div>
  );
}
