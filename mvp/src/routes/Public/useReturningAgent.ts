import { useEffect, useState } from 'react';

// Returning-visitor behaviour for the public landing.
//
// A player who created an agent has `quip:lastAgentId` (localStorage) and, since
// this change, `quip:resumeUrl` — the full /p/{id}#t={token} link that authorises
// their profile across sessions. On a PHONE we send them straight there; on
// DESKTOP we don't hijack the page — Landing shows a "Resume your agent" banner.
//
// A phone visitor who actually wants the landing can append `?stay=1`.

const ID_KEY = 'quip:lastAgentId';
const URL_KEY = 'quip:resumeUrl';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function isPhone(): boolean {
  try {
    return window.matchMedia('(max-width: 540px)').matches;
  } catch {
    return false;
  }
}

function wantsToStay(): boolean {
  try {
    return new URLSearchParams(window.location.search).get('stay') === '1';
  } catch {
    return false;
  }
}

export type ReturningAgent = {
  /** True while a phone redirect is in flight — Landing shows a minimal splash. */
  redirecting: boolean;
  /** Full resume URL (with token) for the desktop banner; null if none stored. */
  resumeUrl: string | null;
  agentId: string | null;
};

export function useReturningAgent(): ReturningAgent {
  const agentId = read(ID_KEY);
  const resumeUrl = read(URL_KEY);
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (!agentId || wantsToStay()) return;
    if (isPhone()) {
      setRedirecting(true);
      // Prefer the tokenised resume URL; fall back to the bare profile route.
      window.location.assign(resumeUrl || `/p/${agentId}`);
    }
    // Desktop: no redirect — the banner handles it.
  }, [agentId, resumeUrl]);

  return { redirecting, resumeUrl: resumeUrl || (agentId ? `/p/${agentId}` : null), agentId };
}
