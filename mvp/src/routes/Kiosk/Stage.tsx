import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

// The kiosk screens are designed on a fixed 1024×768 canvas — a 9.7" iPad in
// landscape. The stage scales that canvas proportionally to whatever the real
// viewport is (Safari chrome, guided-access fullscreen, a desktop window…),
// so the layout always fits exactly, with letterboxing instead of scrolling.
const STAGE_W = 1024;
const STAGE_H = 768;

function fitScale(): number {
  return Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H);
}

export default function KioskStage({ children }: { children: ReactNode }) {
  const [scale, setScale] = useState(fitScale);

  useEffect(() => {
    const update = () => setScale(fitScale());
    window.addEventListener('resize', update);
    window.addEventListener('orientationchange', update);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('orientationchange', update);
    };
  }, []);

  // Touch-kiosk scroll-lock: while the stage is mounted, hard-lock the page so a tablet can't
  // rubber-band / scroll behind the fixed, letterboxed canvas (iOS Safari bounces the body even
  // over a fixed overlay). Scoped via the <html> class so the phone profile + public pages keep
  // scrolling; removed on unmount so navigating away restores normal scroll.
  useEffect(() => {
    const html = document.documentElement;
    html.classList.add('kiosk-locked');
    return () => html.classList.remove('kiosk-locked');
  }, []);

  return (
    <div className="kiosk-stage-viewport">
      <div className="kiosk-stage" style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
        {children}
      </div>
    </div>
  );
}
