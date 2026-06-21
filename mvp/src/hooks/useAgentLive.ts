// One source of truth for "what is live right now" for an agent. Owns the
// subscription (real WebSocket or mock simulator), exposes the latest update and
// the connection status, and tears down cleanly. Consumed by the phone profile
// and the kiosk welcome.

import { useEffect, useState } from 'react';
import type { AgentUpdate, ConnectionStatus } from '../api';
import { subscribeAgent } from '../api';

export type AgentLive = {
  update: AgentUpdate | null;
  status: ConnectionStatus;
};

export function useAgentLive(agentId: string | undefined): AgentLive {
  const [update, setUpdate] = useState<AgentUpdate | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');

  useEffect(() => {
    if (!agentId) {
      setStatus('closed');
      return;
    }
    setStatus('connecting');
    const unsubscribe = subscribeAgent(agentId, setUpdate, { onStatus: setStatus });
    return unsubscribe;
  }, [agentId]);

  return { update, status };
}
