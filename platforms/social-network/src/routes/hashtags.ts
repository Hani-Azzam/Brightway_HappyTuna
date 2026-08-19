import { Router, Request, Response, NextFunction } from 'express';
import { getPostsByHashtag, getTrending } from '../services/hashtagService';
import { optionalAuthenticate } from '../middleware/auth';
import { sendSuccess } from '../utils/response';
import { parsePagination } from '../utils/pagination';

const router = Router();

/**
 * GET /api/hashtags/trending
 * Returns the most-used hashtags in the recent window. Query: ?limit (max 50).
 */
router.get('/trending', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Math.min(parseInt(String(req.query['limit'] ?? '10'), 10) || 10, 50);
    const trending = await getTrending(limit);
    sendSuccess(res, { trending });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/hashtags/:tag
 * Returns posts tagged with :tag (case-insensitive). Paginated.
 */
router.get('/:tag', optionalAuthenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const tag = (req.params['tag'] as string).toLowerCase().replace(/^#/, '');
    const posts = await getPostsByHashtag(tag, parsePagination(req.query), req.user?.id);
    sendSuccess(res, { tag, posts });
  } catch (err) {
    next(err);
  }
});

export default router;
