import { PrismaClient } from '@prisma/client';
import { ASPECTS } from '../analytics/lexicon';
import { isShaper, typeBoost } from '../utils/accountTypes';
import { postInclude, PostWithRelations } from './postService';

const prisma = new PrismaClient();

// --- small numeric helpers -------------------------------------------------

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function stdDev(xs: number[], mu: number): number {
  return xs.length ? Math.sqrt(mean(xs.map((x) => (x - mu) ** 2))) : 0;
}

function round(value: number, dp = 1): number {
  const f = 10 ** dp;
  return Math.round(value * f) / f;
}

function bucketKey(date: Date, bucket: 'hour' | 'day'): string {
  const iso = date.toISOString();
  return bucket === 'day' ? iso.slice(0, 10) : `${iso.slice(0, 13)}:00`;
}

function parseAspects(json: string | null): Record<string, number> {
  if (!json) return {};
  try {
    const obj = JSON.parse(json);
    return obj && typeof obj === 'object' ? (obj as Record<string, number>) : {};
  } catch {
    return {};
  }
}

// --- A. Headline KPIs ------------------------------------------------------

export interface Overview {
  opinionIndex: number;
  weightedOpinionIndex: number;
  sentiment: { positive: number; neutral: number; negative: number };
  shareOfVoice: number;
  crisisMeter: number;
  totals: { posts: number; analyzed: number; companyMentions: number };
}

/** A company post with the fields the headline KPIs need (author type + amplification). */
type CompanyPost = {
  sentimentScore: number | null;
  sentimentLabel: string | null;
  createdAt: Date;
  user: { accountType: string };
  _count: { likes: number; reposts: number };
};

/**
 * Influence-weighted Opinion Index: like the raw index, but each post is weighted by its author's
 * account-type boost and by how far it was amplified (log of likes + reposts). Louder, more-shared
 * voices move it more — so it reads the opinion that is actually *reaching* people.
 */
function weightedOpinionIndex(company: CompanyPost[]): number {
  let weightSum = 0;
  let scoreSum = 0;
  for (const p of company) {
    const amplification = Math.log(1 + p._count.likes + p._count.reposts);
    const weight = typeBoost(p.user.accountType) * (1 + amplification);
    weightSum += weight;
    scoreSum += weight * (p.sentimentScore ?? 0);
  }
  return weightSum ? 100 * (scoreSum / weightSum) : 0;
}

/** Opinion Index, sentiment mix, share of voice, and the Crisis Meter over analyzed company posts. */
export async function getOverview(): Promise<Overview> {
  const analyzed = await prisma.post.findMany({
    where: { analyzedAt: { not: null } },
    select: {
      sentimentScore: true,
      sentimentLabel: true,
      mentionsCompany: true,
      createdAt: true,
      user: { select: { accountType: true } },
      _count: { select: { likes: true, reposts: true } },
    },
  });
  const company = analyzed.filter((p) => p.mentionsCompany);

  const opinionIndex = company.length ? 100 * mean(company.map((p) => p.sentimentScore ?? 0)) : 0;

  const sentiment = { positive: 0, neutral: 0, negative: 0 };
  for (const p of company) {
    if (p.sentimentLabel === 'positive') sentiment.positive++;
    else if (p.sentimentLabel === 'negative') sentiment.negative++;
    else sentiment.neutral++;
  }

  const totalPosts = await prisma.post.count();
  const shareOfVoice = analyzed.length ? company.length / analyzed.length : 0;

  return {
    opinionIndex: round(opinionIndex),
    weightedOpinionIndex: round(weightedOpinionIndex(company)),
    sentiment,
    shareOfVoice: round(shareOfVoice, 3),
    crisisMeter: round(crisisMeter(company)),
    totals: { posts: totalPosts, analyzed: analyzed.length, companyMentions: company.length },
  };
}

/** Crisis Meter (0..100): negative share scaled by recent volume velocity (velocity capped at 1). */
function crisisMeter(company: Array<{ sentimentLabel: string | null; createdAt: Date }>): number {
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const last = company.filter((p) => now - p.createdAt.getTime() <= dayMs);
  const prev = company.filter((p) => {
    const age = now - p.createdAt.getTime();
    return age > dayMs && age <= 2 * dayMs;
  });
  if (last.length === 0) return 0;

  const negShare = last.filter((p) => p.sentimentLabel === 'negative').length / last.length;
  const velocity = Math.min(1, Math.max(0, (last.length - prev.length) / Math.max(prev.length, 1)));
  return Math.max(0, Math.min(1, negShare * (1 + velocity))) * 100;
}

// --- A. Sentiment timeline -------------------------------------------------

export interface TimelineBucket {
  bucket: string;
  volume: number;
  positive: number;
  neutral: number;
  negative: number;
  opinionIndex: number;
}

/** Opinion Index and sentiment mix per time bucket for analyzed company posts. */
export async function getSentimentTimeline(
  bucket: 'hour' | 'day' = 'hour',
  windowHours = 48,
): Promise<TimelineBucket[]> {
  const since = new Date(Date.now() - windowHours * 60 * 60 * 1000);
  const posts = await prisma.post.findMany({
    where: { analyzedAt: { not: null }, mentionsCompany: true, createdAt: { gte: since } },
    select: { createdAt: true, sentimentScore: true, sentimentLabel: true },
    orderBy: { createdAt: 'asc' },
  });

  const groups = new Map<string, { scores: number[]; positive: number; neutral: number; negative: number }>();
  for (const p of posts) {
    const key = bucketKey(p.createdAt, bucket);
    const g = groups.get(key) ?? { scores: [], positive: 0, neutral: 0, negative: 0 };
    g.scores.push(p.sentimentScore ?? 0);
    if (p.sentimentLabel === 'positive') g.positive++;
    else if (p.sentimentLabel === 'negative') g.negative++;
    else g.neutral++;
    groups.set(key, g);
  }

  return [...groups.entries()].map(([key, g]) => ({
    bucket: key,
    volume: g.scores.length,
    positive: g.positive,
    neutral: g.neutral,
    negative: g.negative,
    opinionIndex: round(100 * mean(g.scores)),
  }));
}

// --- B. Aspect-based sentiment ---------------------------------------------

export interface AspectStat {
  key: string;
  label: string;
  volume: number;
  sentiment: number;
}

/** Mean sentiment and volume per tuna aspect across analyzed company posts. */
export async function getAspectSentiment(): Promise<AspectStat[]> {
  const posts = await prisma.post.findMany({
    where: { analyzedAt: { not: null }, mentionsCompany: true },
    select: { aspects: true },
  });

  const scores = new Map<string, number[]>();
  for (const p of posts) {
    for (const [key, value] of Object.entries(parseAspects(p.aspects))) {
      const arr = scores.get(key) ?? [];
      arr.push(value);
      scores.set(key, arr);
    }
  }

  return ASPECTS.map((def) => {
    const arr = scores.get(def.key) ?? [];
    return { key: def.key, label: def.label, volume: arr.length, sentiment: arr.length ? round(100 * mean(arr)) : 0 };
  });
}

// --- B. Trends with sentiment + rising rate --------------------------------

export interface TrendStat {
  tag: string;
  count: number;
  previous: number;
  rising: number;
  sentiment: number;
}

/** Top hashtags in the window with their previous-window count, rising ratio, and mean sentiment. */
export async function getTrends(limit = 10, windowHours = 24): Promise<TrendStat[]> {
  const now = Date.now();
  const curSince = new Date(now - windowHours * 60 * 60 * 1000);
  const prevSince = new Date(now - 2 * windowHours * 60 * 60 * 1000);

  const current = await prisma.postHashtag.groupBy({
    by: ['hashtagId'],
    where: { post: { createdAt: { gte: curSince } } },
    _count: { hashtagId: true },
    orderBy: { _count: { hashtagId: 'desc' } },
    take: limit,
  });
  if (current.length === 0) return [];

  const ids = current.map((c) => c.hashtagId);
  const [tags, previous] = await Promise.all([
    prisma.hashtag.findMany({ where: { id: { in: ids } } }),
    prisma.postHashtag.groupBy({
      by: ['hashtagId'],
      where: { hashtagId: { in: ids }, post: { createdAt: { gte: prevSince, lt: curSince } } },
      _count: { hashtagId: true },
    }),
  ]);
  const tagById = new Map(tags.map((t) => [t.id, t.tag]));
  const prevById = new Map(previous.map((p) => [p.hashtagId, p._count.hashtagId]));

  const result: TrendStat[] = [];
  for (const c of current) {
    const tagged = await prisma.post.findMany({
      where: { analyzedAt: { not: null }, hashtags: { some: { hashtagId: c.hashtagId } } },
      select: { sentimentScore: true },
    });
    const sentiment = tagged.length ? round(100 * mean(tagged.map((p) => p.sentimentScore ?? 0))) : 0;
    const prevCount = prevById.get(c.hashtagId) ?? 0;
    const count = c._count.hashtagId;
    result.push({ tag: tagById.get(c.hashtagId) ?? '', count, previous: prevCount, rising: round(count / (prevCount + 1), 2), sentiment });
  }
  return result;
}

// --- C. Top influencers + stance -------------------------------------------

export interface Influencer {
  id: string;
  name: string;
  accountType: string;
  followers: number;
  repostsReceived: number;
  influence: number;
  stance: number | null;
}

/** Ranks users by influence (followers + reposts received + account-type boost) with their company stance. */
export async function getTopInfluencers(limit = 10): Promise<Influencer[]> {
  const users = await prisma.user.findMany({
    include: { _count: { select: { followers: true } } },
  });

  const influencers: Influencer[] = [];
  for (const u of users) {
    const followers = u._count.followers;
    const repostsReceived = await prisma.repost.count({ where: { post: { userId: u.id } } });
    const influence = Math.log(1 + followers) + 0.5 * Math.log(1 + repostsReceived) + typeBoost(u.accountType);

    const companyPosts = await prisma.post.findMany({
      where: { userId: u.id, analyzedAt: { not: null }, mentionsCompany: true },
      select: { sentimentScore: true },
    });
    const stance = companyPosts.length ? round(100 * mean(companyPosts.map((p) => p.sentimentScore ?? 0))) : null;

    influencers.push({ id: u.id, name: u.name, accountType: u.accountType, followers, repostsReceived, influence: round(influence, 3), stance });
  }

  influencers.sort((a, b) => b.influence - a.influence);
  return influencers.slice(0, limit);
}

// --- D. Spike / event-footprint detection ----------------------------------

export interface Spike {
  bucket: string;
  volume: number;
  zScore: number;
  sentiment: number;
}

/** Flags time buckets whose company-mention volume is >= k std devs above the mean ("detected events"). */
export async function detectSpikes(bucket: 'hour' | 'day' = 'hour', windowHours = 72, k = 2): Promise<Spike[]> {
  const since = new Date(Date.now() - windowHours * 60 * 60 * 1000);
  const posts = await prisma.post.findMany({
    where: { analyzedAt: { not: null }, mentionsCompany: true, createdAt: { gte: since } },
    select: { createdAt: true, sentimentScore: true },
  });

  const groups = new Map<string, number[]>();
  for (const p of posts) {
    const key = bucketKey(p.createdAt, bucket);
    const arr = groups.get(key) ?? [];
    arr.push(p.sentimentScore ?? 0);
    groups.set(key, arr);
  }

  const buckets = [...groups.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1));
  const volumes = buckets.map(([, scores]) => scores.length);
  const mu = mean(volumes);
  const sigma = stdDev(volumes, mu);

  const spikes: Spike[] = [];
  for (const [key, scores] of buckets) {
    const z = sigma > 0 ? (scores.length - mu) / sigma : 0;
    if (z >= k) spikes.push({ bucket: key, volume: scores.length, zScore: round(z, 2), sentiment: round(100 * mean(scores)) });
  }
  return spikes;
}

// --- F. Narrative shapers: cohort split ------------------------------------

export interface CohortStat {
  key: string;
  label: string;
  posts: number;
  authors: number;
  opinionIndex: number;
  positive: number;
  neutral: number;
  negative: number;
}

export interface CohortReport {
  /** One row per account type (regular / influencer / journalist / official). */
  byType: CohortStat[];
  /** Independent narrative shapers: journalists + influencers. */
  shapers: CohortStat;
  /** The general public: regular accounts. */
  publicVoice: CohortStat;
  /** The company's own voice: official account(s). */
  official: CohortStat;
  /** shapers.opinionIndex − publicVoice.opinionIndex: are the loud voices ahead of the public? */
  gap: number;
}

type CohortPost = {
  userId: string;
  sentimentScore: number | null;
  sentimentLabel: string | null;
  user: { accountType: string };
};

/** Rolls a set of posts into a single cohort summary (opinion index + sentiment mix + reach). */
function buildCohort(key: string, label: string, posts: CohortPost[]): CohortStat {
  const authors = new Set(posts.map((p) => p.userId));
  const stat: CohortStat = { key, label, posts: posts.length, authors: authors.size, opinionIndex: 0, positive: 0, neutral: 0, negative: 0 };
  for (const p of posts) {
    if (p.sentimentLabel === 'positive') stat.positive++;
    else if (p.sentimentLabel === 'negative') stat.negative++;
    else stat.neutral++;
  }
  stat.opinionIndex = posts.length ? round(100 * mean(posts.map((p) => p.sentimentScore ?? 0))) : 0;
  return stat;
}

const COHORT_LABELS: Record<string, string> = {
  regular: 'Public',
  influencer: 'Influencers',
  journalist: 'Journalists',
  official: 'Official',
};

/**
 * Splits company sentiment by who is speaking: each account type on its own, plus the headline
 * "shapers (press + creators) vs. the public" comparison and the gap between them. A wide gap means
 * the people with reach are steering opinion away from where the public currently sits.
 */
export async function getCohortSentiment(): Promise<CohortReport> {
  const posts = await prisma.post.findMany({
    where: { analyzedAt: { not: null }, mentionsCompany: true },
    select: { userId: true, sentimentScore: true, sentimentLabel: true, user: { select: { accountType: true } } },
  });

  const byTypePosts = new Map<string, CohortPost[]>();
  for (const p of posts) {
    const arr = byTypePosts.get(p.user.accountType) ?? [];
    arr.push(p);
    byTypePosts.set(p.user.accountType, arr);
  }

  const byType = ['regular', 'influencer', 'journalist', 'official'].map((type) =>
    buildCohort(type, COHORT_LABELS[type] ?? type, byTypePosts.get(type) ?? []),
  );

  const shapers = buildCohort('shapers', 'Press & creators', posts.filter((p) => isShaper(p.user.accountType)));
  const publicVoice = buildCohort('public', 'The public', posts.filter((p) => p.user.accountType === 'regular'));
  const official = buildCohort('official', 'Official', posts.filter((p) => p.user.accountType === 'official'));

  return { byType, shapers, publicVoice, official, gap: round(shapers.opinionIndex - publicVoice.opinionIndex) };
}

// --- F. Narrative shapers: provenance & propagation ------------------------

export interface Narrative {
  tag: string;
  posts: number;
  authors: number;
  sentiment: number;
  /** Who started the tag: an independent shaper, the official company account, or the grassroots public. */
  origin: 'shaper' | 'official' | 'grassroots';
  originator: { id: string; name: string; accountType: string } | null;
  firstSeen: string;
  lastSeen: string;
  /** How many posts under this tag came from each account type — its propagation footprint. */
  byType: { regular: number; influencer: number; journalist: number; official: number };
}

/**
 * Narrative provenance & propagation: for the busiest hashtags, who started it (the originator and
 * whether they were a shaper or an ordinary member of the public), how far it spread (post/author
 * counts and a per-account-type breakdown), and its overall sentiment. This is how we tell a
 * shaper-led narrative apart from a grassroots one.
 */
export async function getNarratives(limit = 8): Promise<Narrative[]> {
  const tags = await prisma.hashtag.findMany({
    include: {
      posts: {
        include: {
          post: {
            select: {
              createdAt: true,
              sentimentScore: true,
              analyzedAt: true,
              user: { select: { id: true, name: true, accountType: true } },
            },
          },
        },
      },
    },
  });

  const narratives: Narrative[] = [];
  for (const t of tags) {
    const posts = t.posts.map((ph) => ph.post).sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
    if (posts.length === 0) continue;

    const byType = { regular: 0, influencer: 0, journalist: 0, official: 0 };
    const authors = new Set<string>();
    const scores: number[] = [];
    for (const p of posts) {
      authors.add(p.user.id);
      if (p.user.accountType in byType) byType[p.user.accountType as keyof typeof byType]++;
      if (p.analyzedAt) scores.push(p.sentimentScore ?? 0);
    }

    const first = posts[0]!;
    const originator = { id: first.user.id, name: first.user.name, accountType: first.user.accountType };
    narratives.push({
      tag: t.tag,
      posts: posts.length,
      authors: authors.size,
      sentiment: scores.length ? round(100 * mean(scores)) : 0,
      origin: isShaper(originator.accountType) ? 'shaper' : originator.accountType === 'official' ? 'official' : 'grassroots',
      originator,
      firstSeen: first.createdAt.toISOString(),
      lastSeen: posts[posts.length - 1]!.createdAt.toISOString(),
      byType,
    });
  }

  narratives.sort((a, b) => b.posts - a.posts || b.authors - a.authors);
  return narratives.slice(0, limit);
}

// --- E. Top posts by engagement --------------------------------------------

export interface TopPost {
  post: PostWithRelations;
  engagement: number;
}

/** Posts ranked by total engagement (likes + reposts + comments). */
export async function getTopPosts(limit = 10): Promise<TopPost[]> {
  const posts = await prisma.post.findMany({ include: postInclude });
  return posts
    .map((post) => ({ post, engagement: post._count.likes + post._count.reposts + post._count.comments }))
    .sort((a, b) => b.engagement - a.engagement)
    .slice(0, limit);
}
