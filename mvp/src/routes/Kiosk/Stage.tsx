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

  return (
    <div className="kiosk-stage-viewport">
      <div className="kiosk-stage" style={{ transform: `scale(${scale})` }}>
        {children}
      </div>
    </div>
  );
}
