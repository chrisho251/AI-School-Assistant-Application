/* useCountdown — a 1-second-tick countdown for the quiz timer.
 * Returns the remaining seconds and an mm:ss label; fires onExpire once at zero. */
import { useEffect, useRef, useState } from 'react';

interface CountdownOptions {
  active?: boolean;
  onExpire?: () => void;
}

export function useCountdown(
  initialSeconds: number,
  { active = true, onExpire }: CountdownOptions = {},
) {
  const [seconds, setSeconds] = useState(initialSeconds);
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;
  const firedRef = useRef(false);

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => {
      setSeconds((s) => {
        if (s <= 1) {
          clearInterval(t);
          if (!firedRef.current) {
            firedRef.current = true;
            onExpireRef.current?.();
          }
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [active]);

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
  const ss = String(seconds % 60).padStart(2, '0');
  return { seconds, label: `${mm}:${ss}` };
}
