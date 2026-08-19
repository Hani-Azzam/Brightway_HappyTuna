import { Prisma, PrismaClient } from '@prisma/client';
import { AppError } from '../utils/errors';
import { Pagination } from '../utils/pagination';
import { extractHashtags } from '../utils/text';

const prisma = new PrismaClient();

/**
 * Shared include shape for a post returned to clients: author, the original post (for quotes),
 * comments with their authors, and engagement counts. Reused across services for consistency.
 */
export const postInclude = Prisma.validator<Prisma.PostInclude>()({
  user: { select: { id: true, name: true, avatar: true, accountType: true } },
  repostOf: {
    include: { user: { select: { id: true, name: true, avatar: true, accountType: true } } },
  },
  comments: {
    include: { user: { select: { id: true, name: true, avatar: true, accountType: true } } },
    orderBy: { createdAt: 'asc' },
  },
  _count: { select: { likes: true, reposts: true, comments: true } },
});
export type PostWithRelations = Prisma.PostGetPayload<{ include: typeof postInclude }>;

/** Minimal author summary attached to an amplified (reposted) timeline entry. */
export type ReposterSummary = { id: string; name: string; avatar: string | null; accountType: string };

/**
 * A post as it appears in a feed. Extends the raw post with:
 * - `reposter`: set when the entry is surfaced because someone reposted the original (amplification);
 *   `null`/absent for an original post shown on its own.
 * - `viewerHasLiked` / `viewerHasReposted`: whether the requesting user has engaged with the post
 *   (both `false` for anonymous requests).
 */
export type PostView = PostWithRelations & {
  reposter?: ReposterSummary | null;
  viewerHasLiked: boolean;
  viewerHasReposted: boolean;
};

/**
 * Annotates posts with the requesting viewer's own like/repost state so clients can render the
 * engagement buttons in their correct on/off position. With no `viewerId` (anonymous request) every
 * flag is `false`. Runs two batched lookups regardless of page size.
 */
export async function attachViewerState<T extends { id: string }>(
  posts: T[],
  viewerId?: string,
): Promise<(T & { viewerHasLiked: boolean; viewerHasReposted: boolean })[]> {
  if (!viewerId || posts.length === 0) {
    return posts.map((p) => ({ ...p, viewerHasLiked: false, viewerHasReposted: false }));
  }
  const postIds = posts.map((p) => p.id);
  const [likes, reposts] = await Promise.all([
    prisma.like.findMany({ where: { userId: viewerId, postId: { in: postIds } }, select: { postId: true } }),
    prisma.repost.findMany({ where: { userId: viewerId, postId: { in: postIds } }, select: { postId: true } }),
  ]);
  const liked = new Set(likes.map((l) => l.postId));
  const reposted = new Set(reposts.map((r) => r.postId));
  return posts.map((p) => ({ ...p, viewerHasLiked: liked.has(p.id), viewerHasReposted: reposted.has(p.id) }));
}

/**
 * Builds a timeline for a set of authors, interleaving their original posts with the posts they have
 * reposted (pure amplification). Each repost surfaces the *original* post carrying a `reposter` label,
 * ordered by when it was surfaced (repost time for reposts, creation time for originals), newest first.
 *
 * If the same post appears both as an original and as a repost, it is shown once at its most recent
 * surfacing. Because the two sources are merged and de-duplicated in memory, a page may occasionally
 * be shorter than `take` near a de-dupe boundary — an accepted trade-off at simulation scale that
 * avoids raw SQL. Returns `[]` when `authorIds` is empty.
 */
export async function getTimeline(
  authorIds: string[],
  pagination: Pagination,
  viewerId?: string,
): Promise<PostView[]> {
  if (authorIds.length === 0) return [];

  // Over-fetch enough of each source that the merged, de-duplicated slice for this page is correct.
  const window = pagination.skip + pagination.take;

  const [posts, reposts] = await Promise.all([
    prisma.post.findMany({
      where: { userId: { in: authorIds } },
      orderBy: { createdAt: 'desc' },
      take: window,
      include: postInclude,
    }),
    prisma.repost.findMany({
      where: { userId: { in: authorIds } },
      orderBy: { createdAt: 'desc' },
      take: window,
      include: {
        user: { select: { id: true, name: true, avatar: true, accountType: true } },
        post: { include: postInclude },
      },
    }),
  ]);

  type Entry = { post: PostWithRelations; reposter: ReposterSummary | null; surfacedAt: Date };
  const entries: Entry[] = [
    ...posts.map((p) => ({ post: p, reposter: null, surfacedAt: p.createdAt })),
    ...reposts.map((r) => ({ post: r.post, reposter: r.user, surfacedAt: r.createdAt })),
  ];

  // Newest surfacing first, then keep only the first occurrence of each original post.
  entries.sort((a, b) => b.surfacedAt.getTime() - a.surfacedAt.getTime());
  const seen = new Set<string>();
  const deduped = entries.filter((e) => (seen.has(e.post.id) ? false : (seen.add(e.post.id), true)));

  const pageEntries = deduped.slice(pagination.skip, pagination.skip + pagination.take);
  return attachViewerState(
    pageEntries.map((e) => ({ ...e.post, reposter: e.reposter })),
    viewerId,
  );
}

/**
 * Creates a post for the given user. Parses `#hashtags` from the content and links them.
 * Optionally references an original post (`repostOfId`) to form a quote-post.
 * Throws 400 if empty or over 500 chars, 404 if the referenced original does not exist.
 */
export async function createPost(
  userId: string,
  content: string,
  repostOfId?: string | null,
): Promise<PostWithRelations> {
  const trimmed = content.trim();
  if (!trimmed) throw new AppError('Post content cannot be empty', 400);
  if (trimmed.length > 500) throw new AppError('Post content exceeds 500 characters', 400);

  if (repostOfId) {
    const original = await prisma.post.findUnique({ where: { id: repostOfId } });
    if (!original) throw new AppError('Original post not found', 404);
  }

  const tags = extractHashtags(trimmed);

  return prisma.post.create({
    data: {
      userId,
      content: trimmed,
      repostOfId: repostOfId ?? null,
      hashtags: {
        create: tags.map((tag) => ({
          hashtag: { connectOrCreate: { where: { tag }, create: { tag } } },
        })),
      },
    },
    include: postInclude,
  });
}

/**
 * Returns posts newest first with author, comments, and engagement counts. Pure reposts are not
 * injected here — the global feed already shows every post to everyone, so amplification is a no-op.
 * `viewerId` (when provided) annotates each post with the requester's like/repost state.
 */
export async function getGlobalFeed(pagination: Pagination, viewerId?: string): Promise<PostView[]> {
  const posts = await prisma.post.findMany({
    orderBy: { createdAt: 'desc' },
    skip: pagination.skip,
    take: pagination.take,
    include: postInclude,
  });
  return attachViewerState(posts, viewerId);
}

/**
 * Returns a single post by id, annotated with the requester's like/repost state. Throws 404 if not found.
 */
export async function getPostById(id: string, viewerId?: string): Promise<PostView> {
  const post = await prisma.post.findUnique({ where: { id }, include: postInclude });
  if (!post) throw new AppError('Post not found', 404);
  const [view] = await attachViewerState([post], viewerId);
  return view!;
}
