import { PrismaClient } from '@prisma/client';
import { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { createAnalyticsMcpServer } from '../analyticsServer';
import { connectToServer, jsonOf } from './mcpTestClient';

const prisma = new PrismaClient();

async function call(client: Client, name: string, args: Record<string, unknown> = {}): Promise<CallToolResult> {
  return (await client.callTool({ name, arguments: args })) as CallToolResult;
}

/** Seeds a user with a couple of company-mentioning posts for the analytics tools to chew on. */
async function seedPosts(): Promise<void> {
  const user = await prisma.user.create({ data: { name: 'analyst-subject' } });
  await prisma.post.createMany({
    data: [
      { userId: user.id, content: 'BrightWay tuna is amazing and sustainable' },
      { userId: user.id, content: 'I am worried about BrightWay tuna safety' },
    ],
  });
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
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('analytics MCP server', () => {
  it('lists the research tools', async () => {
    const client = await connectToServer(createAnalyticsMcpServer());
    const { tools } = await client.listTools();
    const names = tools.map((t) => t.name);
    expect(names).toEqual(
      expect.arrayContaining(['get_overview', 'get_sentiment_timeline', 'get_cohort_sentiment', 'run_analysis', 'set_ai_analysis']),
    );
  });

  it('returns a well-formed overview after analysis', async () => {
    await seedPosts();
    const client = await connectToServer(createAnalyticsMcpServer());

    const run = jsonOf<{ analyzed: number; engine: string }>(await call(client, 'run_analysis', {}));
    expect(run.analyzed).toBe(2);
    expect(run.engine).toBe('lexicon');

    const overview = jsonOf<{ opinionIndex: number; totals: { posts: number; analyzed: number } }>(
      await call(client, 'get_overview', {}),
    );
    expect(overview.totals.posts).toBe(2);
    expect(overview.totals.analyzed).toBe(2);
    expect(typeof overview.opinionIndex).toBe('number');
  });

  it('reports and toggles analysis status', async () => {
    const client = await connectToServer(createAnalyticsMcpServer());

    const before = jsonOf<{ aiAnalysisEnabled: boolean }>(await call(client, 'get_analysis_status', {}));
    const toggled = jsonOf<{ aiAnalysisEnabled: boolean }>(await call(client, 'set_ai_analysis', { enabled: !before.aiAnalysisEnabled }));
    expect(toggled.aiAnalysisEnabled).toBe(!before.aiAnalysisEnabled);

    // reset so the runtime toggle doesn't leak into other tests
    await call(client, 'set_ai_analysis', { enabled: before.aiAnalysisEnabled });
  });

  it('exposes a cohort breakdown shape', async () => {
    await seedPosts();
    const client = await connectToServer(createAnalyticsMcpServer());
    await call(client, 'run_analysis', {});

    const cohorts = jsonOf<{ byType: unknown[]; gap: number }>(await call(client, 'get_cohort_sentiment', {}));
    expect(Array.isArray(cohorts.byType)).toBe(true);
    expect(typeof cohorts.gap).toBe('number');
  });

  it('exercises the full research toolset', async () => {
    await seedPosts();
    const client = await connectToServer(createAnalyticsMcpServer());
    await call(client, 'run_analysis', { reanalyze: true });

    expect(Array.isArray(jsonOf(await call(client, 'get_sentiment_timeline', { bucket: 'day', window: 72 })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_aspect_sentiment')))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_trends', { limit: 5 })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_top_influencers', { limit: 5 })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'detect_spikes', { bucket: 'hour', window: 48, k: 1.5 })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_narratives', { limit: 5 })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_top_posts', { limit: 5 })))).toBe(true);

    // drill-in reads
    expect(jsonOf<{ posts: unknown[] }>(await call(client, 'search', { q: 'tuna' })).posts).toBeDefined();
    expect(Array.isArray(jsonOf(await call(client, 'get_hashtag_posts', { tag: 'tuna' })))).toBe(true);
  });

  it('surfaces a not-found drill-in read as a tool error', async () => {
    const client = await connectToServer(createAnalyticsMcpServer());
    const res = await call(client, 'get_post', { id: 'does-not-exist' });
    expect(res.isError).toBe(true);
  });
});
