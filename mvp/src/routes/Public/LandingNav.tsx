import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

// Slim sticky nav. The brand mark is the official Quip butterfly SVG (media kit).
// Background turns from transparent to blurred-white once the hero scrolls under it.
// The top-right action is EITHER "Resume your agent" (a returning visitor, when a
// resume URL is known) OR "Create your agent" — never both.
export default function LandingNav({ resumeUrl }: { resumeUrl?: string | null }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <nav className={`qpub-nav${scrolled ? ' is-scrolled' : ''}`} aria-label="Primary">
      <a href="#top" className="qpub-brand">
        <img src="/brand/quip-icon-standard-XL-on-light.svg" alt="" className="qpub-bfly" width={22} height={22} />
        <span>Quip Network</span>
      </a>
      <div className="qpub-nav-links">
        <a href="#how">How it works</a>
        <a href="#leaderboard">Leaderboard</a>
        {resumeUrl
          ? <a href={resumeUrl} className="qpub-nav-cta">Resume your agent</a>
          : <Link to="/kiosk" className="qpub-nav-cta">Create your agent</Link>}
      </div>
    </nav>
  );
}
