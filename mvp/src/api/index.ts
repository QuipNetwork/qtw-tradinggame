export * from './types';
export * from './assets';
export { storeAgentToken } from './token';

import * as mocks from './mocks';
import * as real from './real';

// No VITE_API_BASE ⇒ the mock adapter is in use (offline/demo). Surfaces read
// this to show a "Demo data" badge so simulated data is never mistaken for live.
export const IS_MOCK = !import.meta.env.VITE_API_BASE;

const api = IS_MOCK ? mocks : real;

export const submitAgent = api.submitAgent;
export const getAgent = api.getAgent;
export const updateAgent = api.updateAgent;
export const requestOptimization = api.requestOptimization;
export const getLeaderboard = api.getLeaderboard;
export const getRoutingStats = api.getRoutingStats;
export const getValuationHistory = api.getValuationHistory;
export const subscribeAgent = api.subscribeAgent;
export const subscribeTvEvents = api.subscribeTvEvents;
