import { PrismaClient } from '@prisma/client';
import { AppError } from '../utils/errors';

const prisma = new PrismaClient();

async function ensurePostExists(postId: string): Promise<void> {
  const post = await prisma.post.findUnique({ where: { id: postId } });
  if (!post) throw new AppError('Post not found', 404);
}

/**
 * Likes a post on behalf of a user. Throws 404 if the post is missing, 409 if already liked.
 */
export async function likePost(userId: string, postId: string): Promise<void> {
  await ensurePostExists(postId);
  const existing = await prisma.like.findUnique({ where: { userId_postId: { userId, postId } } });
  if (existing) throw new AppError('Already liked', 409);
  await prisma.like.create({ data: { userId, postId } });
}

/**
 * Removes a like. Throws 404 if the user has not liked the post.
 */
export async function unlikePost(userId: string, postId: string): Promise<void> {
  const existing = await prisma.like.findUnique({ where: { userId_postId: { userId, postId } } });
  if (!existing) throw new AppError('Not liked', 404);
  await prisma.like.delete({ where: { userId_postId: { userId, postId } } });
}

/**
 * Reposts (pure amplification) a post. Throws 404 if the post is missing, 409 if already reposted.
 */
export async function repostPost(userId: string, postId: string): Promise<void> {
  await ensurePostExists(postId);
  const existing = await prisma.repost.findUnique({ where: { userId_postId: { userId, postId } } });
  if (existing) throw new AppError('Already reposted', 409);
  await prisma.repost.create({ data: { userId, postId } });
}

/**
 * Removes a repost. Throws 404 if the user has not reposted the post.
 */
export async function unrepostPost(userId: string, postId: string): Promise<void> {
  const existing = await prisma.repost.findUnique({ where: { userId_postId: { userId, postId } } });
  if (!existing) throw new AppError('Not reposted', 404);
  await prisma.repost.delete({ where: { userId_postId: { userId, postId } } });
}
