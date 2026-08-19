import { Router, Request, Response, NextFunction } from 'express';
import {
  analyzePosts,
  getAnalysisStatus,
} from '../services/sentimentService';
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
} from '../services/analyticsService';
import { setAiAnalysisEnabled } from '../analytics/settings';
import { sendSuccess, sendError } from '../utils/response';

const router = Router();

/**
 * GET /api/analytics/config
 * Current AI-toggle / engine state and analysis coverage.
 */
router.get('/config', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    sendSuccess(res, await getAnalysisStatus());
  } catch (err) {
    next(err);
  }
});

/**
 * PUT /api/analytics/config
 * Turns AI (Claude) sentiment analysis on/off. Body: { aiAnalysisEnabled: boolean }.
 */
router.put('/config', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { aiAnalysisEnabled } = req.body as { aiAnalysisEnabled?: unknown };
    if (typeof aiAnalysisEnabled !== 'boolean') {
      sendError(res, 'aiAnalysisEnabled (boolean) is required', 400);
      return;
    }
    setAiAnalysisEnabled(aiAnalysisEnabled);
    sendSuccess(res, await getAnalysisStatus());
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/analytics/analyze
 * Runs on-demand analysis. Body: { reanalyze?: boolean } — reanalyze recomputes every post.
 */
router.post('/analyze', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { reanalyze } = req.body as { reanalyze?: boolean };
    const result = await analyzePosts(Boolean(reanalyze));
    sendSuccess(res, result);
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/overview — headline KPIs (opinion index, sentiment, share of voice, crisis meter). */
router.get('/overview', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    sendSuccess(res, await getOverview());
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/sentiment/timeline?bucket=hour|day&window=hours */
router.get('/sentiment/timeline', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const bucket = req.query['bucket'] === 'day' ? 'day' : 'hour';
    const windowHours = Math.max(1, parseInt(String(req.query['window'] ?? '48'), 10) || 48);
    sendSuccess(res, { timeline: await getSentimentTimeline(bucket, windowHours) });
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/aspects — aspect-based sentiment. */
router.get('/aspects', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    sendSuccess(res, { aspects: await getAspectSentiment() });
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/trends — trending tags with rising rate + sentiment. */
router.get('/trends', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Math.min(parseInt(String(req.query['limit'] ?? '10'), 10) || 10, 50);
    sendSuccess(res, { trends: await getTrends(limit) });
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/influencers — top influencers and their company stance. */
router.get('/influencers', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Math.min(parseInt(String(req.query['limit'] ?? '10'), 10) || 10, 50);
    sendSuccess(res, { influencers: await getTopInfluencers(limit) });
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/spikes?bucket=hour|day&window=hours&k=z — detected event footprints. */
router.get('/spikes', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const bucket = req.query['bucket'] === 'day' ? 'day' : 'hour';
    const windowHours = Math.max(1, parseInt(String(req.query['window'] ?? '72'), 10) || 72);
    const k = Number(req.query['k'] ?? '2') || 2;
    sendSuccess(res, { spikes: await detectSpikes(bucket, windowHours, k) });
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/top-posts — most-engaged posts. */
router.get('/top-posts', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Math.min(parseInt(String(req.query['limit'] ?? '10'), 10) || 10, 50);
    sendSuccess(res, { posts: await getTopPosts(limit) });
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/cohorts — sentiment split by who is speaking (shapers vs. public). */
router.get('/cohorts', async (_req: Request, res: Response, next: NextFunction) => {
  try {
    sendSuccess(res, await getCohortSentiment());
  } catch (err) {
    next(err);
  }
});

/** GET /api/analytics/narratives — hashtag provenance & propagation (who started it, how it spread). */
router.get('/narratives', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Math.min(parseInt(String(req.query['limit'] ?? '8'), 10) || 8, 50);
    sendSuccess(res, { narratives: await getNarratives(limit) });
  } catch (err) {
    next(err);
  }
});

export default router;
