export * from './types';
export * from './assets';

import * as mocks from './mocks';
import * as real from './real';

const api = import.meta.env.VITE_API_BASE ? real : mocks;

export const submitAgent = api.submitAgent;
export const getAgent = api.getAgent;
export const updateAgent = api.updateAgent;
export const requestOptimization = api.requestOptimization;
export const getLeaderboard = api.getLeaderboard;
export const getRoutingStats = api.getRoutingStats;
export const getValuationHistory = api.getValuationHistory;
export const subscribeAgent = api.subscribeAgent;
