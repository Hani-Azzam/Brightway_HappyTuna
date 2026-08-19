import { Router, Request, Response, NextFunction } from 'express';
import { createPost, getGlobalFeed, getPostById } from '../services/postService';
import { createComment, getCommentsByPost } from '../services/commentService';
import { likePost, unlikePost, repostPost, unrepostPost } from '../services/engagementService';
import { authenticate, optionalAuthenticate } from '../middleware/auth';
import { sendSuccess } from '../utils/response';
import { parsePagination } from '../utils/pagination';

const router = Router();

/**
 * GET /api/posts
 * Global feed — posts newest first with comments and engagement counts (public). Paginated.
 */
router.get('/', optionalAuthenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const posts = await getGlobalFeed(parsePagination(req.query), req.user?.id);
    sendSuccess(res, { posts });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/posts/:id
 * Returns a single post with comments (public).
 */
router.get('/:id', optionalAuthenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const post = await getPostById(req.params['id'] as string, req.user?.id);
    sendSuccess(res, { post });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/posts
 * Creates a post as the authenticated user. Body: { content, repostOfId? }.
 * Providing repostOfId makes this a quote-post of the referenced original.
 */
router.post('/', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { content, repostOfId } = req.body as { content?: string; repostOfId?: string };
    const post = await createPost(req.user!.id, content ?? '', repostOfId ?? null);
    sendSuccess(res, { post }, 201);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/posts/:id/comments
 * Returns all comments on a post (public).
 */
router.get('/:id/comments', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const comments = await getCommentsByPost(req.params['id'] as string);
    sendSuccess(res, { comments });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/posts/:id/comments
 * Creates a comment on a post as the authenticated user. Body: { content }.
 */
router.post('/:id/comments', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { content } = req.body as { content?: string };
    const comment = await createComment(req.params['id'] as string, req.user!.id, content ?? '');
    sendSuccess(res, { comment }, 201);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/posts/:id/like — like a post as the authenticated user.
 */
router.post('/:id/like', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    await likePost(req.user!.id, req.params['id'] as string);
    sendSuccess(res, { message: 'Liked' }, 201);
  } catch (err) {
    next(err);
  }
});

/**
 * DELETE /api/posts/:id/like — remove a like.
 */
router.delete('/:id/like', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    await unlikePost(req.user!.id, req.params['id'] as string);
    sendSuccess(res, { message: 'Unliked' });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/posts/:id/repost — repost (pure amplification) as the authenticated user.
 */
router.post('/:id/repost', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    await repostPost(req.user!.id, req.params['id'] as string);
    sendSuccess(res, { message: 'Reposted' }, 201);
  } catch (err) {
    next(err);
  }
});

/**
 * DELETE /api/posts/:id/repost — undo a repost.
 */
router.delete('/:id/repost', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    await unrepostPost(req.user!.id, req.params['id'] as string);
    sendSuccess(res, { message: 'Unreposted' });
  } catch (err) {
    next(err);
  }
});

export default router;
