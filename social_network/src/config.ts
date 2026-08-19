/**
 * Centralized configuration module. All env vars must be accessed through here.
 */

function requireEnv(key: string): string {
  const value = process.env[key];
  if (!value) throw new Error(`Missing required environment variable: ${key}`);
  return value;
}

export const config = {
  port: parseInt(process.env['PORT'] ?? '3000', 10),
  nodeEnv: process.env['NODE_ENV'] ?? 'development',
  databaseUrl: requireEnv('DATABASE_URL'),
  /** Allowed CORS origin for the API. Defaults to '*' (security is out of scope in this sim). */
  corsOrigin: process.env['CORS_ORIGIN'] ?? '*',
  /**
   * The tuna company whose public opinion the platform measures. Set via COMPANY_NAME — the name
   * is not hardcoded anywhere in the app or UI; everything (detection + labels) derives from here.
   * The default is the bundled demo brand; set COMPANY_NAME to the real name when it is known.
   */
  companyName: process.env['COMPANY_NAME'] ?? 'HappyTuna',
  /**
   * Extra company-detection terms (alternate spellings, handles, cashtags), comma-separated.
   * The company name itself (with and without spaces) is always matched; these are additions.
   * e.g. COMPANY_ALIASES="happy tuna,$happy,#happytuna".
   */
  companyAliases: (process.env['COMPANY_ALIASES'] ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
  /** This product's own brand name (ours), shown in the UI. Set via PLATFORM_NAME. */
  platformName: process.env['PLATFORM_NAME'] ?? 'BrightTweets',
  /** Default state of the AI (Claude) sentiment toggle; can be flipped at runtime via the API. */
  aiAnalysisDefault: (process.env['AI_ANALYSIS_ENABLED'] ?? 'false').toLowerCase() === 'true',
  /** Optional. When set AND the AI toggle is on, analytics use Claude; otherwise the lexicon. */
  get anthropicApiKey(): string | undefined {
    return process.env['ANTHROPIC_API_KEY'];
  },
};
