import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getLeaderboard, type LeaderboardEntry } from '../../api';
import LandingNav from './LandingNav';
import Hero from './Hero';
import HowItWorks from './HowItWorks';
import LiveLeaderboard from './LiveLeaderboard';
import Spotlight from './Spotlight';
import { useReturningAgent } from './useReturningAgent';
import { useReveal } from './useReveal';
import './landing.css';

// Public landing surface (`/`). Showcase + resume: hero, how-it-works, live
// leaderboard, top-10 spotlight. Agent creation stays booth-gated — the CTA
// routes to /kiosk. One source of leaderboard truth, polled here and shared with
// the board + spotlight so they never drift.
export default function Landing() {
  useReveal();
  const { redirecting, resumeUrl } = useReturningAgent();
  const [board, setBoard] = useState<LeaderboardEntry[]>([]);

  useEffect(() => {
    let alive = true;
    const pull = () => getLeaderboard().then(b => { if (alive) setBoard(b); }).catch(() => {});
    pull();
    const t = setInterval(pull, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (redirecting) {
    return (
      <div className="qpub qpub-splash">
        <span className="qpub-livedot" />
        <p>Opening your agent…</p>
      </div>
    );
  }

  return (
    <div className="qpub" id="top">
      <LandingNav resumeUrl={resumeUrl} />

      <main className="qpub-page">
        <Hero resumeUrl={resumeUrl} />
        <HowItWorks />
        <LiveLeaderboard rows={board} />
        <Spotlight agent={board[0] ?? null} />

        <section className="qpub-band" data-reveal>
          <h2>Your agent is one tap away.</h2>
          <p>Create it at the booth and follow it from your phone.</p>
          <Link to="/kiosk" className="qpub-btn qpub-btn-solid lg">Create your agent <span aria-hidden>→</span></Link>
        </section>
      </main>

      <footer className="qpub-foot">
        <img src="/brand/quip-lockup-horizontal-standard-on-light.svg" alt="Quip Network" className="qpub-foot-mark" height={22} />
        <span className="qpub-foot-note">Virtual portfolios · no real trading</span>
        <a className="qpub-foot-link" href="https://quip.network" target="_blank" rel="noreferrer">quip.network ↗</a>
      </footer>
    </div>
  );
}
