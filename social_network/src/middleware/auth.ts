import { Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import { sendError } from '../utils/response';

const prisma = new PrismaClient();

export interface AuthUser {
  id: string;
  name: string;
  accountType: string;
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

/**
 * Authenticates a request via `Authorization: Bearer <userId>`. The token is simply the user id
 * (security is out of scope in this simulation). Loads the user and attaches it to `req.user`.
 * Responds 401 if the header is missing or the id is unknown.
 */
export async function authenticate(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith('Bearer ')) {
      sendError(res, 'Authorization token required', 401);
      return;
    }

    const token = authHeader.slice(7).trim();
    const user = await prisma.user.findUnique({ where: { id: token } });
    if (!user) {
      sendError(res, 'Invalid token', 401);
      return;
    }

    req.user = { id: user.id, name: user.name, accountType: user.accountType };
    next();
  } catch (err) {
    next(err as Error);
  }
}

/**
 * Best-effort authentication for public read endpoints. If a valid `Authorization: Bearer <userId>`
 * header is present it attaches `req.user` (so responses can be personalized, e.g. viewer like/repost
 * state); otherwise it proceeds anonymously without erroring. Never responds 401.
 */
export async function optionalAuthenticate(req: Request, _res: Response, next: NextFunction): Promise<void> {
  try {
    const authHeader = req.headers.authorization;
    if (authHeader?.startsWith('Bearer ')) {
      const token = authHeader.slice(7).trim();
      const user = await prisma.user.findUnique({ where: { id: token } });
      if (user) req.user = { id: user.id, name: user.name, accountType: user.accountType };
    }
    next();
  } catch (err) {
    next(err as Error);
  }
}
