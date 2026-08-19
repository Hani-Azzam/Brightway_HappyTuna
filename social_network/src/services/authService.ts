import { PrismaClient, User } from '@prisma/client';
import { AppError } from '../utils/errors';

const prisma = new PrismaClient();

export interface LoginResult {
  token: string;
  user: User;
}

/**
 * Logs a user in by name only — no password and no separate signup step.
 * Upserts the unique name and returns the user plus a bearer token. The token is simply the
 * user id: authentication is intentionally out of scope for this simulation.
 * Throws 400 if the name is empty or longer than 50 characters.
 */
export async function login(name: string): Promise<LoginResult> {
  const trimmed = name.trim();
  if (!trimmed) throw new AppError('name is required', 400);
  if (trimmed.length > 50) throw new AppError('name exceeds 50 characters', 400);

  const user = await prisma.user.upsert({
    where: { name: trimmed },
    update: {},
    create: { name: trimmed },
  });

  return { token: user.id, user };
}
