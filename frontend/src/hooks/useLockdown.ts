/* useLockdown — browser-side exam proctoring. Ports the JS from
 * ui/components/lockdown.html to a React hook: while `active`, it listens for
 * tab-switch / blur / fullscreen-exit / context-menu / copy / blocked keys and
 * POSTs each as a proctor event via the ApiClient (no iframe bridge needed here,
 * unlike Streamlit). Returns the running violation count.
 *
 * Fullscreen is entered from the Start button's click gesture in QuizScreen (a
 * requestFullscreen from an effect would be rejected as non-user-initiated); this
 * hook only reports when the student leaves it. */
import { useEffect, useState } from 'react';

import { useApi } from '@/lib/auth';

const BLOCKED_KEYS = ['c', 'v', 'p', 'u'];

export function useLockdown(attemptId: string | null, active: boolean): number {
  const api = useApi();
  const [violations, setViolations] = useState(0);

  useEffect(() => {
    if (!active || !attemptId || !api) return;

    const report = (type: string, payload: Record<string, unknown> = {}) => {
      setViolations((v) => v + 1);
      // Drop the event on a network hiccup rather than break the exam.
      api.recordProctorEvent(attemptId, type, payload).catch(() => {});
    };

    const onVisibility = () => {
      if (document.hidden) report('tab_hidden');
    };
    const onBlur = () => report('window_blur');
    const onFullscreen = () => {
      if (!document.fullscreenElement) report('fullscreen_exit');
    };
    const onContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      report('context_menu');
    };
    const onCopy = (e: ClipboardEvent) => {
      e.preventDefault();
      report('copy');
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const k = (e.key || '').toLowerCase();
      const blocked = e.key === 'F12' || ((e.ctrlKey || e.metaKey) && BLOCKED_KEYS.includes(k));
      if (blocked) {
        e.preventDefault();
        report('key_blocked', { key: e.key });
      }
    };

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', onBlur);
    document.addEventListener('fullscreenchange', onFullscreen);
    document.addEventListener('contextmenu', onContextMenu);
    document.addEventListener('copy', onCopy);
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', onBlur);
      document.removeEventListener('fullscreenchange', onFullscreen);
      document.removeEventListener('contextmenu', onContextMenu);
      document.removeEventListener('copy', onCopy);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [active, attemptId, api]);

  return violations;
}
