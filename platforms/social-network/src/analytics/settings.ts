import { config } from '../config';

/**
 * Runtime toggle for AI (Claude) sentiment analysis. Defaults from AI_ANALYSIS_ENABLED but can be
 * flipped on/off at any time via the analytics API. In-memory only — resets to the default on
 * restart (acceptable for this simulation).
 */
let aiAnalysisEnabled = config.aiAnalysisDefault;

export function isAiAnalysisEnabled(): boolean {
  return aiAnalysisEnabled;
}

export function setAiAnalysisEnabled(value: boolean): void {
  aiAnalysisEnabled = value;
}
