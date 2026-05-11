import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getLeaderboard } from '../../api';
import type { LeaderboardEntry } from '../../api';
import StateA from './StateA';
import StateB from './StateB';
import StateC from './StateC';
import StateD from './StateD';

type StateName = 'A' | 'B' | 'C' | 'D';

// Production rotation: 12s leaderboard → 15s spotlight → 20s intro → repeat,
// stepping through ranks 1..10. State D interrupts for 10s on new agent.
const TIMINGS: Record<StateName, number> = { A: 12000, B: 15000, C: 20000, D: 10000 };

export default function BoothTV() {
  const [params] = useSearchParams();
  const forced = params.get('state') as StateName | null;

  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[] | null>(null);
  const [state, setState] = useState<StateName>('A');
  const [spotIndex, setSpotIndex] = useState(0);

  useEffect(() => {
    getLeaderboard().then(setLeaderboard);
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

  if (!leaderboard) {
    return <div style={{ width: '100vw', height: '100vh', background: '#0a0a10' }} />;
  }

  const active = forced ?? state;

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
        {active === 'A' && <StateA leaderboard={leaderboard} />}
        {active === 'B' && <StateB leaderboard={leaderboard} rankIndex={spotIndex} />}
        {active === 'C' && <StateC />}
        {active === 'D' && <StateD />}
      </div>
    </div>
  );
}
