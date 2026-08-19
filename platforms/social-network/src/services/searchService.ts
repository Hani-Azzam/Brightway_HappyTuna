import { PrismaClient } from '@prisma/client';
import { AppError } from '../utils/errors';
import { Pagination } from '../utils/pagination';
import { attachViewerState, postInclude, PostView } from './postService';

const prisma = new PrismaClient();

export interface SearchResults {
  users: Array<{ id: string; name: string; avatar: string | null; accountType: string }>;
  posts: PostView[];
  hashtags: Array<{ id: string; tag: string }>;
}

/**
 * Free-text search across users (by name), posts (by content), and hashtags (by tag).
 * Matching is case-insensitive (SQLite LIKE). Throws 400 if the query is empty.
 * `viewerId` (when provided) annotates each matched post with the requester's like/repost state.
 */
export async function search(q: string, pagination: Pagination, viewerId?: string): Promise<SearchResults> {
  const query = q.trim();
  if (!query) throw new AppError('q is required', 400);
  const tagQuery = query.replace(/^#/, '').toLowerCase();

  const [users, posts, hashtags] = await Promise.all([
    prisma.user.findMany({
      where: { name: { contains: query } },
      select: { id: true, name: true, avatar: true, accountType: true },
      take: pagination.take,
      skip: pagination.skip,
    }),
    prisma.post.findMany({
      where: { content: { contains: query } },
      orderBy: { createdAt: 'desc' },
      take: pagination.take,
      skip: pagination.skip,
      include: postInclude,
    }),
    prisma.hashtag.findMany({
      where: { tag: { contains: tagQuery } },
      select: { id: true, tag: true },
      take: pagination.take,
    }),
  ]);

  return { users, posts: await attachViewerState(posts, viewerId), hashtags };
}
