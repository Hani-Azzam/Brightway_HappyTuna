import { Router, Request, Response, NextFunction } from 'express';
import { login } from '../services/authService';
import { sendSuccess } from '../utils/response';

const router = Router();

/**
 * POST /api/auth/login
 * Name-only login. Body: { name }. Creates the user if the name is new.
 * Returns { token, user } where token is the user id.
 */
router.post('/login', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { name } = req.body as { name?: string };
    const result = await login(name ?? '');
    sendSuccess(res, result);
  } catch (err) {
    next(err);
  }
});

export default router;
