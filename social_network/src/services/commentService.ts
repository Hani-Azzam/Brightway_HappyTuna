import { Prisma, PrismaClient } from '@prisma/client';
import { AppError } from '../utils/errors';

const prisma = new PrismaClient();

const commentArgs = Prisma.validator<Prisma.CommentDefaultArgs>()({
  include: { user: { select: { id: true, name: true, avatar: true, accountType: true } } },
});
export type CommentWithUser = Prisma.CommentGetPayload<typeof commentArgs>;

/**
 * Creates a comment on a post from the given user.
 * Throws 400 if empty or over 280 characters, 404 if the post does not exist.
 */
export async function createComment(
  postId: string,
  userId: string,
  content: string,
): Promise<CommentWithUser> {
  const trimmed = content.trim();
  if (!trimmed) throw new AppError('Comment content cannot be empty', 400);
  if (trimmed.length > 280) throw new AppError('Comment exceeds 280 characters', 400);

  const post = await prisma.post.findUnique({ where: { id: postId } });
  if (!post) throw new AppError('Post not found', 404);

  return prisma.comment.create({
    data: { postId, userId, content: trimmed },
    include: commentArgs.include,
  });
}

/**
 * Returns all comments for a post, oldest first. Throws 404 if the post does not exist.
 */
export async function getCommentsByPost(postId: string): Promise<CommentWithUser[]> {
  const post = await prisma.post.findUnique({ where: { id: postId } });
  if (!post) throw new AppError('Post not found', 404);

  return prisma.comment.findMany({
    where: { postId },
    orderBy: { createdAt: 'asc' },
    include: commentArgs.include,
  });
}
