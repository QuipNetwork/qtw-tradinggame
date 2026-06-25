import { useEffect } from 'react';

// Scroll-reveal: fades/raises elements tagged `data-reveal` into place as they
// enter the viewport. Respects prefers-reduced-motion (everything shown at once).
// One shared observer per mount; cheap enough for a single landing page.
export function useReveal() {
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const nodes = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));
    if (reduce || !('IntersectionObserver' in window)) {
      nodes.forEach(n => n.classList.add('is-revealed'));
      return;
    }
    const io = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            obs.unobserve(entry.target);
          }
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 },
    );
    nodes.forEach(n => io.observe(n));
    return () => io.disconnect();
  }, []);
}
