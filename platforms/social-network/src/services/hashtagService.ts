import { PrismaClient } from '@prisma/client';
import { Pagination } from '../utils/pagination';
import { attachViewerState, postInclude, PostView } from './postService';

const prisma = new PrismaClient();

export interface TrendingTag {
  tag: string;
  count: number;
}

/**
 * Returns posts tagged with the given hashtag (case-insensitive, leading '#' optional), newest first.
 * `viewerId` (when provided) annotates each post with the requester's like/repost state.
 */
export async function getPostsByHashtag(
  tag: string,
  pagination: Pagination,
  viewerId?: string,
): Promise<PostView[]> {
  const normalized = tag.toLowerCase().replace(/^#/, '');
  const posts = await prisma.post.findMany({
    where: { hashtags: { some: { hashtag: { tag: normalized } } } },
    orderBy: { createdAt: 'desc' },
    skip: pagination.skip,
    take: pagination.take,
    include: postInclude,
  });
  return attachViewerState(posts, viewerId);
}

/**
 * Returns the most-used hashtags within the last `windowHours`, highest count first.
 * (Phase 3 analytics extends this with rising-rate and per-topic sentiment.)
 */
export async function getTrending(limit = 10, windowHours = 24): Promise<TrendingTag[]> {
  const since = new Date(Date.now() - windowHours * 60 * 60 * 1000);

  const grouped = await prisma.postHashtag.groupBy({
    by: ['hashtagId'],
    where: { post: { createdAt: { gte: since } } },
    _count: { hashtagId: true },
    orderBy: { _count: { hashtagId: 'desc' } },
    take: limit,
  });
  if (grouped.length === 0) return [];

  const hashtags = await prisma.hashtag.findMany({
    where: { id: { in: grouped.map((g) => g.hashtagId) } },
  });
  const tagById = new Map(hashtags.map((h) => [h.id, h.tag]));

  return grouped.map((g) => ({ tag: tagById.get(g.hashtagId) ?? '', count: g._count.hashtagId }));
}
