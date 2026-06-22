import { useEffect, useRef, useState } from 'react';

// A money/number value that flashes green when it ticks up and red when it ticks
// down — like a live trading board. Keep it mounted with a stable list key (e.g.
// per ticker / per agent) so it remembers the previous value across re-renders
// and reshuffles; the inner span re-keys on each change to replay the flash.
// Reduced motion is handled globally (the flash is a CSS animation).
export default function TickValue({
  value,
  text,
  className,
}: {
  value: number;
  text: string;
  className?: string;
}) {
  const prevRef = useRef(value);
  const [tick, setTick] = useState(0);
  const [dir, setDir] = useState<'up' | 'down' | ''>('');

  useEffect(() => {
    if (value === prevRef.current) return;
    setDir(value > prevRef.current ? 'up' : 'down');
    setTick(t => t + 1);
    prevRef.current = value;
  }, [value]);

  return (
    <span className={[className, 'tickv', dir].filter(Boolean).join(' ')} key={tick}>
      {text}
    </span>
  );
}
