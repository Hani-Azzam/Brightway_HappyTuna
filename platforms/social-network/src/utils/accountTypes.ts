/**
 * Account types and influence weighting, shared by the platform and the analytics engine.
 * SQLite has no enums, so `User.accountType` is a free string validated through this module.
 * See docs/analytics-methodology.md (Narrative shapers) for how the weights are used.
 */

/** Every account type the platform recognises. `regular` is the default ("the public"). */
export const ACCOUNT_TYPES = ['regular', 'influencer', 'journalist', 'official'] as const;
export type AccountType = (typeof ACCOUNT_TYPES)[number];

/**
 * Account types that independently shape public narrative. The `official` company account is
 * deliberately excluded: it is the company's own voice (PR), not independent opinion, so the
 * cohort split reports it separately rather than lumping it with the press/creators.
 */
export const SHAPER_TYPES: ReadonlySet<string> = new Set(['influencer', 'journalist']);

/** Type guard: is `value` one of the allowed account types? */
export function isAccountType(value: unknown): value is AccountType {
  return typeof value === 'string' && (ACCOUNT_TYPES as readonly string[]).includes(value);
}

/** True when the account type is an independent narrative shaper (influencer or journalist). */
export function isShaper(accountType: string): boolean {
  return SHAPER_TYPES.has(accountType);
}

/**
 * Influence multiplier per account type. Shapers (journalist/influencer) carry 1.5× the weight of
 * a regular voice; the official account is kept at 1× so company PR does not inflate the metrics.
 */
export const TYPE_BOOST: Record<string, number> = { regular: 1, influencer: 1.5, journalist: 1.5, official: 1 };

/** Influence multiplier for an account type; unknown types default to 1. */
export function typeBoost(accountType: string): number {
  return TYPE_BOOST[accountType] ?? 1;
}
