/** Chart colors (mirror the design tokens; Recharts needs explicit hex values). */
export const C = {
  tide: '#1C9DEC',
  deepTide: '#1483CC',
  kelp: '#17BF63',
  coral: '#E0245E',
  slate: '#536471',
  sand: '#F0B429',
  hairline: '#E5EBF0',
  ink: '#0F1419',
  neutral: '#9aa7b1',
} as const;

export function sentimentClass(v: number): 'pos' | 'neg' | 'neu' {
  return v > 5 ? 'pos' : v < -5 ? 'neg' : 'neu';
}

export function sentimentColor(v: number): string {
  return v > 5 ? C.kelp : v < -5 ? C.coral : C.slate;
}

export function crisisBand(v: number): { label: string; color: string } {
  if (v < 30) return { label: 'Calm', color: C.kelp };
  if (v < 60) return { label: 'Watch', color: C.sand };
  if (v < 80) return { label: 'Elevated', color: '#F97316' };
  return { label: 'Crisis', color: C.coral };
}

/** "2026-06-24T10:00" → "10:00"; "2026-06-24" → "Jun 24". */
export function fmtBucket(bucket: string): string {
  if (bucket.includes('T')) return bucket.slice(11, 16);
  const d = new Date(bucket);
  return Number.isNaN(d.getTime()) ? bucket : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
