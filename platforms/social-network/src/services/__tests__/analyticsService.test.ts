import { PrismaClient } from '@prisma/client';
import { createPost } from '../postService';
import { analyzePosts } from '../sentimentService';
import {
  getOverview,
  getSentimentTimeline,
  getAspectSentiment,
  getTrends,
  getTopInfluencers,
  detectSpikes,
  getTopPosts,
  getCohortSentiment,
  getNarratives,
} from '../analyticsService';
import { setAiAnalysisEnabled } from '../../analytics/settings';

const prisma = new PrismaClient();

function createUser(name: string, accountType = 'regular') {
  return prisma.user.create({ data: { name, accountType } });
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();
  setAiAnalysisEnabled(false);
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('analytics over a small scenario', () => {
  it('computes overview, aspects, trends, influencers, timeline, and top posts', async () => {
    const official = await createUser('brightway_tuna', 'official');
    const fan = await createUser('fan', 'influencer');
    const critic = await createUser('critic');
    await createUser('lurker'); // no posts -> stance null branch

    const p1 = await createPost(official.id, 'Proud sustainable pole-and-line BrightWay tuna #brightway #dolphinsafe');
    await createPost(fan.id, 'Love the fresh delicious BrightWay melt #brightway');
    await createPost(critic.id, 'BrightWay tuna is gross, saltier and a total scam #brightway');
    await createPost(fan.id, 'unrelated post about cats');

    await prisma.follow.create({ data: { followerId: fan.id, followingId: official.id } });
    await prisma.follow.create({ data: { followerId: critic.id, followingId: official.id } });
    await prisma.repost.create({ data: { userId: fan.id, postId: p1.id } });
    await prisma.like.create({ data: { userId: critic.id, postId: p1.id } });

    await analyzePosts();

    const overview = await getOverview();
    expect(overview.totals.companyMentions).toBe(3);
    expect(overview.sentiment.negative).toBe(1);
    expect(overview.sentiment.positive).toBeGreaterThanOrEqual(2);
    expect(overview.shareOfVoice).toBeGreaterThan(0);

    const aspects = await getAspectSentiment();
    expect(aspects).toHaveLength(6);
    expect(aspects.find((a) => a.key === 'taste')!.volume).toBeGreaterThan(0);

    const trends = await getTrends();
    expect(trends.find((t) => t.tag === 'brightway')!.count).toBe(3);

    const influencers = await getTopInfluencers();
    const off = influencers.find((i) => i.name === 'brightway_tuna')!;
    expect(off.followers).toBe(2);
    expect(off.repostsReceived).toBe(1);
    expect(off.stance).not.toBeNull();
    expect(influencers.find((i) => i.name === 'lurker')!.stance).toBeNull();

    const timeline = await getSentimentTimeline('hour', 48);
    expect(timeline.length).toBeGreaterThan(0);

    const top = await getTopPosts();
    expect(top[0]!.engagement).toBeGreaterThan(0);
  });

  it('detects a volume spike across time buckets', async () => {
    const u = await createUser('spiker', 'official');
    const analyzed = { mentionsCompany: true, sentimentScore: -0.3, sentimentLabel: 'negative', analyzedAt: new Date() };

    // four quiet hourly buckets...
    for (const hoursAgo of [6, 5, 4, 3]) {
      await prisma.post.create({
        data: { userId: u.id, content: 'BrightWay #brightway', createdAt: new Date(Date.now() - hoursAgo * 3600 * 1000), ...analyzed },
      });
    }
    // ...then a loud recent one
    for (let i = 0; i < 8; i++) {
      await prisma.post.create({
        data: { userId: u.id, content: `BrightWay ${i} #brightway`, createdAt: new Date(Date.now() - 3600 * 1000), ...analyzed },
      });
    }

    const spikes = await detectSpikes('hour', 72, 1.5);
    expect(spikes.length).toBeGreaterThan(0);
    expect(spikes[0]!.volume).toBe(8);
  });

  it('returns safe zeros when nothing has been analyzed', async () => {
    const overview = await getOverview();
    expect(overview.opinionIndex).toBe(0);
    expect(overview.weightedOpinionIndex).toBe(0);
    expect(overview.totals.companyMentions).toBe(0);
    expect(await getTrends()).toEqual([]);
    expect(await detectSpikes()).toEqual([]);
    expect(await getNarratives()).toEqual([]);
  });
});

describe('narrative-shaper analytics', () => {
  it('splits sentiment by cohort and traces narrative provenance', async () => {
    const journalist = await createUser('maria', 'journalist');
    const influencer = await createUser('sam', 'influencer');
    const fan = await createUser('tom'); // regular = "the public"
    const official = await createUser('bw', 'official');

    // A journalist breaks the concern first, then an influencer amplifies it.
    await createPost(journalist.id, 'BrightWay mercury found in tuna, a total scam #brightwaymercury #brightway');
    await createPost(influencer.id, 'Pausing BrightWay, the mercury concern is gross #brightwaymercury #brightway');
    await createPost(fan.id, 'Love the fresh delicious BrightWay melt #brightway');
    await createPost(official.id, 'Proud sustainable BrightWay tuna #brightway');

    await analyzePosts();

    const cohorts = await getCohortSentiment();
    expect(cohorts.byType).toHaveLength(4);
    expect(cohorts.shapers.posts).toBe(2);
    expect(cohorts.publicVoice.posts).toBe(1);
    expect(cohorts.official.posts).toBe(1);
    // shapers are negative here, the public is positive -> negative gap
    expect(cohorts.shapers.opinionIndex).toBeLessThan(cohorts.publicVoice.opinionIndex);
    expect(cohorts.gap).toBeLessThan(0);

    const narratives = await getNarratives();
    const mercury = narratives.find((n) => n.tag === 'brightwaymercury')!;
    expect(mercury).toBeDefined();
    expect(mercury.origin).toBe('shaper');
    expect(mercury.originator!.name).toBe('maria');
    expect(mercury.posts).toBe(2);
    expect(mercury.authors).toBe(2);
    expect(mercury.byType.journalist).toBe(1);
    expect(mercury.byType.influencer).toBe(1);

    const overview = await getOverview();
    expect(typeof overview.weightedOpinionIndex).toBe('number');
  });

  it('handles neutral posts, official-led tags, empty cohorts, and unanalyzed posts', async () => {
    const official = await createUser('bw2', 'official');
    const joe = await createUser('joe'); // regular

    await createPost(official.id, 'BrightWay posts an operations update today #brightwayops'); // neutral
    await createPost(joe.id, 'BrightWay tuna is delicious and fresh #brightwayops'); // positive
    await analyzePosts();
    // a third post under the same tag that is never analyzed
    await createPost(joe.id, 'Another BrightWay note #brightwayops');

    const cohorts = await getCohortSentiment();
    const journalists = cohorts.byType.find((c) => c.key === 'journalist')!;
    expect(journalists.posts).toBe(0); // empty cohort -> opinionIndex 0 branch
    expect(journalists.opinionIndex).toBe(0);
    expect(cohorts.shapers.posts).toBe(0);
    expect(cohorts.official.posts).toBe(1);

    const narratives = await getNarratives();
    const ops = narratives.find((n) => n.tag === 'brightwayops')!;
    expect(ops.origin).toBe('official'); // official-led branch
    expect(ops.posts).toBe(3); // includes the unanalyzed post
    expect(ops.byType.official).toBe(1);
    expect(ops.byType.regular).toBe(2);
  });
});
