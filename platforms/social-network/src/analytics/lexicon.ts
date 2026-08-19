/**
 * Deterministic sentiment + topic lexicon for the tuna domain.
 * Used directly when the AI toggle is off, and as the fallback when Claude analysis fails.
 * See docs/analytics-methodology.md for the formulas.
 */

import { config } from '../config';

export const POSITIVE_THRESHOLD = 0.15;
export const NEGATIVE_THRESHOLD = -0.15;

/**
 * Lowercased substrings that mark a post as mentioning the company, derived from the configured
 * company name (with and without spaces) plus any `COMPANY_ALIASES`. Nothing brand-specific is
 * hardcoded — change `COMPANY_NAME` and detection follows. e.g. "Happy Tuna" → matches
 * "happy tuna", "happytuna", "@happytuna", "#happytuna".
 */
export function companyKeywords(): string[] {
  const terms = new Set<string>();
  const name = config.companyName.toLowerCase().trim();
  if (name) {
    terms.add(name);
    terms.add(name.replace(/\s+/g, ''));
  }
  for (const alias of config.companyAliases) {
    const t = alias.toLowerCase().trim();
    if (t) terms.add(t);
  }
  return [...terms];
}

export interface AspectDef {
  key: string;
  label: string;
  keywords: string[];
}

/** Tuna-specific opinion facets. Keywords are matched as lowercased substrings. */
export const ASPECTS: AspectDef[] = [
  { key: 'sustainability', label: 'Sustainability / Dolphin-safe', keywords: ['dolphin', 'dolphinsafe', 'dolphin-safe', 'bycatch', 'overfish', 'sustainab', 'pole-and-line', 'pole and line', 'ocean', 'stewardship', 'msc'] },
  { key: 'health', label: 'Health / Mercury', keywords: ['mercury', 'contaminat', 'toxin', 'fda', 'omega-3', 'omega 3', 'protein', 'pregnan', 'health', 'nutrition'] },
  { key: 'price', label: 'Price / Value', keywords: ['price', 'pricier', 'expensive', 'cheap', 'cost', 'afford', 'value', 'inflation', 'budget', 'overpriced'] },
  { key: 'taste', label: 'Taste / Quality', keywords: ['taste', 'tasty', 'fresh', 'flavor', 'quality', 'texture', 'mushy', 'bland', 'delicious', 'meaty', 'salty', 'saltier', 'yummy'] },
  { key: 'ethics', label: 'Ethics / Labor', keywords: ['labor', 'worker', 'wage', 'forced labor', 'slavery', 'supply chain', 'ethical', 'exploit'] },
  { key: 'safety', label: 'Safety / Recall', keywords: ['recall', 'contaminated', 'listeria', 'botulism', 'sick', 'poison', 'lawsuit', 'outbreak'] },
];

const POSITIVE = new Set([
  'love', 'loved', 'great', 'delicious', 'fresh', 'best', 'amazing', 'good', 'tasty', 'affordable',
  'worth', 'proud', 'sustainable', 'quality', 'recommend', 'excellent', 'happy', 'support',
  'beautiful', 'unreal', 'finally', 'win', 'meaty', 'healthy', 'clean', 'perfect', 'delight',
]);

const NEGATIVE = new Set([
  'hate', 'bad', 'gross', 'salty', 'saltier', 'expensive', 'pricey', 'pricier', 'recall',
  'contaminated', 'sick', 'poison', 'lawsuit', 'mushy', 'bland', 'worse', 'worst', 'disgusting',
  'skeptical', 'doubt', 'concern', 'concerned', 'mercury', 'toxin', 'scam', 'avoid', 'boycott',
  'overpriced', 'disappointing', 'disappointed', 'terrible', 'awful',
]);

const NEGATORS = new Set(['not', 'no', 'never', 'dont', 'isnt', 'wasnt', 'hardly', 'without', 'cant', 'cannot']);

export type SentimentLabel = 'positive' | 'neutral' | 'negative';

export interface Analysis {
  sentimentScore: number;
  sentimentLabel: SentimentLabel;
  aspects: Record<string, number>;
  mentionsCompany: boolean;
}

/** Maps a score in [-1, 1] to a label using the configured thresholds. */
export function labelFor(score: number): SentimentLabel {
  if (score > POSITIVE_THRESHOLD) return 'positive';
  if (score < NEGATIVE_THRESHOLD) return 'negative';
  return 'neutral';
}

function tokenize(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9']+/g) ?? [];
}

/** True if the text references the company (per the configured name/aliases). */
export function detectCompany(text: string): boolean {
  const lower = text.toLowerCase();
  return companyKeywords().some((k) => lower.includes(k));
}

/** Returns the aspect keys the text touches. */
export function detectAspects(text: string): string[] {
  const lower = text.toLowerCase();
  return ASPECTS.filter((a) => a.keywords.some((k) => lower.includes(k))).map((a) => a.key);
}

/** Lexicon polarity in (-1, 1): smoothed (pos - neg) / (pos + neg + 1) with simple negation. */
export function lexiconScore(text: string): number {
  const tokens = tokenize(text);
  let pos = 0;
  let neg = 0;
  for (let i = 0; i < tokens.length; i++) {
    const word = tokens[i]!;
    const negated = i > 0 && NEGATORS.has(tokens[i - 1]!);
    if (POSITIVE.has(word)) negated ? neg++ : pos++;
    else if (NEGATIVE.has(word)) negated ? pos++ : neg++;
  }
  if (pos + neg === 0) return 0;
  return (pos - neg) / (pos + neg + 1);
}

/** Full deterministic analysis of a post: sentiment, aspects (attributed the post score), company mention. */
export function lexiconAnalyze(text: string): Analysis {
  const score = lexiconScore(text);
  const aspects: Record<string, number> = {};
  for (const key of detectAspects(text)) aspects[key] = score;
  return { sentimentScore: score, sentimentLabel: labelFor(score), aspects, mentionsCompany: detectCompany(text) };
}
