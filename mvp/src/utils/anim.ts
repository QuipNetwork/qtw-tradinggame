// Dependency-free animation primitives. CSS keyframes/transitions live in
// shared-design/v4-mocks.css; this module covers the numeric tweening the booth
// needs (P&L, totals, weights counting toward a new value) and the reduced-motion
// signal. Everything here snaps instantly when the OS asks for reduced motion.

import { useEffect, useRef, useState } from 'react';

export const linear = (t: number) => t;
export const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);
export const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

// Tracks the OS "reduce motion" setting so callers can snap instead of animate.
export function useReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)';
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia?.(query).matches,
  );
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

type TweenOpts = { durationMs?: number; easing?: (t: number) => number };

// Smoothly interpolates a displayed number toward `target` with requestAnimationFrame.
// On each new target it eases from wherever the display currently sits, so rapid
// ticks chase smoothly rather than snapping. Reduced motion (or a non-finite
// target) short-circuits to an instant set.
export function useTween(target: number, opts: TweenOpts = {}): number {
  const { durationMs = 700, easing = easeOutCubic } = opts;
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);
  const rafRef = useRef(0);

  // Keep a ref in sync so each tween can start from the latest painted value
  // without re-subscribing the effect every frame.
  displayRef.current = display;

  useEffect(() => {
    if (reduced || !Number.isFinite(target) || durationMs <= 0) {
      setDisplay(target);
      return;
    }
    const from = displayRef.current;
    let start = 0;
    const step = (ts: number) => {
      if (!start) start = ts;
      const t = Math.min(1, (ts - start) / durationMs);
      setDisplay(from + (target - from) * easing(t));
      if (t < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
    // displayRef is intentionally read (not a dep) so the tween isn't restarted
    // every frame; we only re-aim when the target/motion/duration changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, reduced, durationMs]);

  return display;
}

// Like useTween but eases several values together in ONE rAF loop committing a
// single state update per frame — so a surface with multiple live numbers (the
// phone P&L: total + $ + %) re-renders once per frame, not three times.
export function useTweens(targets: number[], opts: TweenOpts = {}): number[] {
  const { durationMs = 700, easing = easeOutCubic } = opts;
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(targets);
  const displayRef = useRef(targets);
  const rafRef = useRef(0);
  displayRef.current = display;
  const key = targets.join(',');

  useEffect(() => {
    if (reduced || durationMs <= 0) {
      setDisplay(targets);
      return;
    }
    const from = displayRef.current.length === targets.length ? displayRef.current : targets;
    let start = 0;
    const step = (ts: number) => {
      if (!start) start = ts;
      const t = Math.min(1, (ts - start) / durationMs);
      setDisplay(targets.map((target, i) => {
        const f = from[i] ?? target;
        return Number.isFinite(target) ? f + (target - f) * easing(t) : target;
      }));
      if (t < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
    // Re-aim only when the target set / motion / duration changes (see useTween).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, reduced, durationMs]);

  return display;
}
