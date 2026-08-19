import { Router, Request, Response, NextFunction } from 'express';
import { getAllUsers, getUserById, getFollowing, getUserPosts, updateAccountType, followUser, unfollowUser, getFeed } from '../services/userService';
import { authenticate, optionalAuthenticate } from '../middleware/auth';
import { sendSuccess, sendError } from '../utils/response';
import { parsePagination } from '../utils/pagination';

const router = Router();

/**
 * GET /api/users
 * Returns all users (public), paginated via ?page&limit.
 */
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const users = await getAllUsers(parsePagination(req.query));
    sendSuccess(res, { users });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/users/:id
 * Returns a single user profile (public).
 */
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const user = await getUserById(req.params['id'] as string);
    sendSuccess(res, { user });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/users/:id/posts
 * Returns a user's own posts (public, paginated).
 */
router.get('/:id/posts', optionalAuthenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const posts = await getUserPosts(req.params['id'] as string, parsePagination(req.query), req.user?.id);
    sendSuccess(res, { posts });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/users/:id/following
 * Returns the accounts :id follows (public, paginated).
 */
router.get('/:id/following', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const users = await getFollowing(req.params['id'] as string, parsePagination(req.query));
    sendSuccess(res, { users });
  } catch (err) {
    next(err);
  }
});

/**
 * PATCH /api/users/:id
 * Sets the authenticated user's own account type. Body: { accountType }. Token user must match :id.
 */
router.patch('/:id', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id } = req.params as { id: string };
    if (req.user!.id !== id) {
      sendError(res, 'Cannot modify another user', 403);
      return;
    }
    const { accountType } = req.body as { accountType?: unknown };
    if (typeof accountType !== 'string') {
      sendError(res, 'accountType (string) is required', 400);
      return;
    }
    const user = await updateAccountType(id, accountType);
    sendSuccess(res, { user });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /api/users/:id/follow/:targetId
 * The authenticated user (:id) follows :targetId. Token user must match :id.
 */
router.post('/:id/follow/:targetId', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id, targetId } = req.params as { id: string; targetId: string };
    if (req.user!.id !== id) {
      sendError(res, 'Cannot act on behalf of another user', 403);
      return;
    }
    await followUser(id, targetId);
    sendSuccess(res, { message: 'Followed successfully' });
  } catch (err) {
    next(err);
  }
});

/**
 * DELETE /api/users/:id/follow/:targetId
 * The authenticated user (:id) unfollows :targetId. Token user must match :id.
 */
router.delete('/:id/follow/:targetId', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id, targetId } = req.params as { id: string; targetId: string };
    if (req.user!.id !== id) {
      sendError(res, 'Cannot act on behalf of another user', 403);
      return;
    }
    await unfollowUser(id, targetId);
    sendSuccess(res, { message: 'Unfollowed successfully' });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/users/:id/feed
 * Returns the personalized feed (posts from followed accounts). Token user must match :id.
 */
router.get('/:id/feed', authenticate, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { id } = req.params as { id: string };
    if (req.user!.id !== id) {
      sendError(res, "Cannot access another user's feed", 403);
      return;
    }
    const posts = await getFeed(id, parsePagination(req.query), req.user!.id);
    sendSuccess(res, { posts });
  } catch (err) {
    next(err);
  }
});

export default router;
