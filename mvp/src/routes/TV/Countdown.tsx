import { useEffect, useState } from 'react';

// Counts down from `seconds` to 0. Each TV state remounts on a rotation change,
// so the countdown re-syncs to the new phase naturally.
export default function Countdown({ seconds }: { seconds: number }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    setLeft(seconds);
    const id = window.setInterval(() => setLeft(s => (s > 0 ? s - 1 : 0)), 1000);
    return () => window.clearInterval(id);
  }, [seconds]);
  return <>{left}s</>;
}
