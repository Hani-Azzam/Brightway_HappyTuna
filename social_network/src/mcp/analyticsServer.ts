import { z } from 'zod';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { parsePagination } from '../utils/pagination';
import { runTool } from './toolHelpers';
import { setAiAnalysisEnabled } from '../analytics/settings';
import * as analyticsService from '../services/analyticsService';
import * as sentimentService from '../services/sentimentService';
import * as postService from '../services/postService';
import * as hashtagService from '../services/hashtagService';
import * as searchService from '../services/searchService';

const bucketSchema = z.enum(['hour', 'day']).optional();
const limitSchema = z.number().int().positive().max(50).optional();

/**
 * Creates the **research** MCP server: read-mostly tools over the sentiment-analytics layer for an
 * observer bot to "read the room" — headline KPIs, sentiment timeline, aspect/trend/cohort/narrative
 * breakdowns, spike detection, and top posts/influencers — plus the analyze/config controls and a few
 * drill-in reads (search, get a post, posts by hashtag). No auth: analytics is unauthenticated by design.
 */
export function createAnalyticsMcpServer(): McpServer {
  const server = new McpServer({ name: 'brighttweets-analytics', version: '1.0.0' });

  // --- headline & timeline -------------------------------------------------

  server.registerTool(
    'get_overview',
    {
      title: 'Opinion overview',
      description: 'Headline KPIs: opinion index, weighted opinion index, sentiment mix, share of voice, crisis meter.',
      inputSchema: {},
    },
    async () => runTool(() => analyticsService.getOverview()),
  );

  server.registerTool(
    'get_sentiment_timeline',
    {
      title: 'Sentiment timeline',
      description: 'Opinion index and sentiment mix per time bucket for company posts.',
      inputSchema: { bucket: bucketSchema, window: z.number().int().positive().optional().describe('Window in hours (default 48).') },
    },
    async ({ bucket, window }) => runTool(() => analyticsService.getSentimentTimeline(bucket, window)),
  );

  // --- breakdowns ----------------------------------------------------------

  server.registerTool(
    'get_aspect_sentiment',
    {
      title: 'Aspect sentiment',
      description: 'Mean sentiment and volume per tuna aspect (sustainability, health, price, taste, ethics, safety).',
      inputSchema: {},
    },
    async () => runTool(() => analyticsService.getAspectSentiment()),
  );

  server.registerTool(
    'get_trends',
    {
      title: 'Hashtag trends',
      description: 'Top hashtags with previous-window count, rising ratio, and mean sentiment.',
      inputSchema: { limit: limitSchema },
    },
    async ({ limit }) => runTool(() => analyticsService.getTrends(limit)),
  );

  server.registerTool(
    'get_top_influencers',
    {
      title: 'Top influencers',
      description: 'Users ranked by influence (followers + reposts received + account-type boost) with company stance.',
      inputSchema: { limit: limitSchema },
    },
    async ({ limit }) => runTool(() => analyticsService.getTopInfluencers(limit)),
  );

  server.registerTool(
    'detect_spikes',
    {
      title: 'Detect spikes',
      description: 'Time buckets whose company-mention volume is >= k std devs above the mean ("detected events").',
      inputSchema: {
        bucket: bucketSchema,
        window: z.number().int().positive().optional().describe('Window in hours (default 72).'),
        k: z.number().positive().optional().describe('Z-score threshold (default 2).'),
      },
    },
    async ({ bucket, window, k }) => runTool(() => analyticsService.detectSpikes(bucket, window, k)),
  );

  server.registerTool(
    'get_cohort_sentiment',
    {
      title: 'Cohort sentiment',
      description: 'Company sentiment split by cohort (public vs. shapers vs. official) plus the shaper-vs-public gap.',
      inputSchema: {},
    },
    async () => runTool(() => analyticsService.getCohortSentiment()),
  );

  server.registerTool(
    'get_narratives',
    {
      title: 'Narratives',
      description: 'For the busiest hashtags: who started it (shaper/official/grassroots), spread, and sentiment.',
      inputSchema: { limit: limitSchema },
    },
    async ({ limit }) => runTool(() => analyticsService.getNarratives(limit)),
  );

  server.registerTool(
    'get_top_posts',
    {
      title: 'Top posts',
      description: 'Posts ranked by total engagement (likes + reposts + comments).',
      inputSchema: { limit: limitSchema },
    },
    async ({ limit }) => runTool(() => analyticsService.getTopPosts(limit)),
  );

  // --- analysis controls ---------------------------------------------------

  server.registerTool(
    'get_analysis_status',
    {
      title: 'Analysis status',
      description: 'Current AI toggle/engine state and analysis coverage (total vs analyzed posts).',
      inputSchema: {},
    },
    async () => runTool(() => sentimentService.getAnalysisStatus()),
  );

  server.registerTool(
    'run_analysis',
    {
      title: 'Run analysis',
      description: 'Batch-analyze posts. By default only un-analyzed posts; pass reanalyze to recompute all.',
      inputSchema: { reanalyze: z.boolean().optional() },
    },
    async ({ reanalyze }) => runTool(() => sentimentService.analyzePosts(reanalyze ?? false)),
  );

  server.registerTool(
    'set_ai_analysis',
    {
      title: 'Toggle AI analysis',
      description: 'Enable/disable the Claude sentiment engine at runtime (falls back to the lexicon when off).',
      inputSchema: { enabled: z.boolean() },
    },
    async ({ enabled }) =>
      runTool(async () => {
        setAiAnalysisEnabled(enabled);
        return sentimentService.getAnalysisStatus();
      }),
  );

  // --- drill-in reads ------------------------------------------------------

  server.registerTool(
    'search',
    { title: 'Search', description: 'Free-text search across users, posts, and hashtags.', inputSchema: { q: z.string() } },
    async ({ q }) => runTool(() => searchService.search(q, parsePagination({}))),
  );

  server.registerTool(
    'get_post',
    { title: 'Get a post', description: 'A single post with author, comments, and engagement counts.', inputSchema: { id: z.string() } },
    async ({ id }) => runTool(() => postService.getPostById(id)),
  );

  server.registerTool(
    'get_hashtag_posts',
    {
      title: 'Posts by hashtag',
      description: 'Posts tagged with a hashtag (leading # optional, case-insensitive), newest first.',
      inputSchema: { tag: z.string() },
    },
    async ({ tag }) => runTool(() => hashtagService.getPostsByHashtag(tag, parsePagination({}))),
  );

  return server;
}
