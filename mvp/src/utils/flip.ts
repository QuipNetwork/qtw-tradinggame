import { useLayoutEffect, useRef } from 'react';

// FLIP (First · Last · Invert · Play) reordering for a re-sortable list. When the
// rows inside the container change order between renders, each row glides from its
// previous position to the new one instead of snapping — the "climbing the board"
// effect on the TV leaderboard.
//
// Tag each row with `data-flip-key` (a stable identity, e.g. the agent id) and
// pass an `orderKey` that changes only when the order changes, so the animation
// fires on a real reshuffle rather than on every value tick.
export function useFlipList<T extends HTMLElement>(orderKey: string) {
  const ref = useRef<T>(null);
  const prevTops = useRef<Map<string, number>>(new Map());

  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) return;
    const rows = container.querySelectorAll<HTMLElement>('[data-flip-key]');
    const nextTops = new Map<string, number>();
    rows.forEach(row => {
      const key = row.dataset.flipKey;
      if (!key) return;
      const top = row.offsetTop;
      nextTops.set(key, top);
      const prev = prevTops.current.get(key);
      if (prev !== undefined && prev !== top) {
        // Invert: jump back to the old position with no transition…
        const dy = prev - top;
        row.style.transition = 'none';
        row.style.transform = `translateY(${dy}px)`;
        // …then Play: next frame, glide to the natural (new) position.
        requestAnimationFrame(() => {
          row.style.transition = 'transform 600ms cubic-bezier(0.22, 1, 0.36, 1)';
          row.style.transform = 'translateY(0)';
        });
      }
    });
    prevTops.current = nextTops;
  }, [orderKey]);

  return ref;
}
