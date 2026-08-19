import { Prisma, PrismaClient } from '@prisma/client';
import { AppError } from '../utils/errors';
import { Pagination } from '../utils/pagination';
import { ACCOUNT_TYPES, isAccountType } from '../utils/accountTypes';
import { getTimeline, PostView } from './postService';

const prisma = new PrismaClient();

const userArgs = Prisma.validator<Prisma.UserDefaultArgs>()({
  include: { _count: { select: { posts: true, followers: true, following: true } } },
});
export type UserWithCounts = Prisma.UserGetPayload<typeof userArgs>;

/**
 * Returns users newest first with their post/follower/following counts.
 */
export async function getAllUsers(pagination: Pagination): Promise<UserWithCounts[]> {
  return prisma.user.findMany({
    orderBy: { createdAt: 'desc' },
    skip: pagination.skip,
    take: pagination.take,
    include: userArgs.include,
  });
}

/**
 * Returns a single user profile with relation counts. Throws 404 if not found.
 */
export async function getUserById(id: string): Promise<UserWithCounts> {
  const user = await prisma.user.findUnique({ where: { id }, include: userArgs.include });
  if (!user) throw new AppError('User not found', 404);
  return user;
}

/**
 * Sets a user's account type (regular / influencer / journalist / official). This is how the bot
 * team designates the narrative shapers the analytics dashboard then tracks.
 * Throws 400 on an invalid type and 404 if the user does not exist.
 */
export async function updateAccountType(id: string, accountType: string): Promise<UserWithCounts> {
  if (!isAccountType(accountType)) {
    throw new AppError(`Invalid account type. Allowed: ${ACCOUNT_TYPES.join(', ')}`, 400);
  }
  const user = await prisma.user.findUnique({ where: { id } });
  if (!user) throw new AppError('User not found', 404);

  await prisma.user.update({ where: { id }, data: { accountType } });
  return getUserById(id);
}

/**
 * Creates a follow edge. Throws 400 on self-follow, 404 if the target is missing, 409 if already following.
 */
export async function followUser(followerId: string, followingId: string): Promise<void> {
  if (followerId === followingId) throw new AppError('Cannot follow yourself', 400);

  const target = await prisma.user.findUnique({ where: { id: followingId } });
  if (!target) throw new AppError('Target user not found', 404);

  const existing = await prisma.follow.findUnique({
    where: { followerId_followingId: { followerId, followingId } },
  });
  if (existing) throw new AppError('Already following', 409);

  await prisma.follow.create({ data: { followerId, followingId } });
}

/**
 * Removes a follow edge. Throws 404 if not currently following.
 */
export async function unfollowUser(followerId: string, followingId: string): Promise<void> {
  const existing = await prisma.follow.findUnique({
    where: { followerId_followingId: { followerId, followingId } },
  });
  if (!existing) throw new AppError('Not following this user', 404);

  await prisma.follow.delete({
    where: { followerId_followingId: { followerId, followingId } },
  });
}

export type UserSummary = { id: string; name: string; avatar: string | null; accountType: string };

/**
 * Returns the accounts a user follows (summaries), newest follow first.
 */
export async function getFollowing(userId: string, pagination: Pagination): Promise<UserSummary[]> {
  const follows = await prisma.follow.findMany({
    where: { followerId: userId },
    orderBy: { createdAt: 'desc' },
    skip: pagination.skip,
    take: pagination.take,
    include: { following: { select: { id: true, name: true, avatar: true, accountType: true } } },
  });
  return follows.map((f) => f.following);
}

/**
 * Returns a user's own timeline, newest first: the posts they authored interleaved with the posts
 * they reposted (each carrying a `reposter` label). `viewerId` annotates the requester's engagement state.
 */
export async function getUserPosts(
  userId: string,
  pagination: Pagination,
  viewerId?: string,
): Promise<PostView[]> {
  return getTimeline([userId], pagination, viewerId);
}

/**
 * Returns the personalized feed for a user: original posts and reposts from the accounts they follow,
 * newest first. A followed account's repost amplifies the original post into this feed with a
 * `reposter` label. `viewerId` annotates the requester's engagement state.
 */
export async function getFeed(
  userId: string,
  pagination: Pagination,
  viewerId?: string,
): Promise<PostView[]> {
  const follows = await prisma.follow.findMany({ where: { followerId: userId } });
  const followingIds = follows.map((f) => f.followingId);
  return getTimeline(followingIds, pagination, viewerId);
}
