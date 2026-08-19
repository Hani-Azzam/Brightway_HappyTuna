import { PrismaClient } from '@prisma/client';
import { getAllUsers, getUserById, updateAccountType, followUser, unfollowUser, getFeed, getUserPosts } from '../userService';
import { AppError } from '../../utils/errors';

const prisma = new PrismaClient();
const page = { skip: 0, take: 20 };

function createUser(name: string, accountType = 'regular') {
  return prisma.user.create({ data: { name, accountType } });
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.user.deleteMany();
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('getAllUsers', () => {
  it('returns an empty array when no users exist', async () => {
    expect(await getAllUsers(page)).toEqual([]);
  });

  it('returns users with relation counts', async () => {
    await createUser('u1');
    const users = await getAllUsers(page);
    expect(users).toHaveLength(1);
    expect(users[0]!._count.posts).toBe(0);
  });
});

describe('getUserById', () => {
  it('returns the user when found', async () => {
    const u = await createUser('findme', 'journalist');
    const found = await getUserById(u.id);
    expect(found.name).toBe('findme');
    expect(found.accountType).toBe('journalist');
  });

  it('throws 404 when not found', async () => {
    await expect(getUserById('nonexistent-id')).rejects.toThrow(AppError);
  });
});

describe('updateAccountType', () => {
  it('updates a user to a valid account type', async () => {
    const u = await createUser('typer');
    const updated = await updateAccountType(u.id, 'influencer');
    expect(updated.accountType).toBe('influencer');
  });

  it('throws 400 on an invalid account type', async () => {
    const u = await createUser('typer2');
    await expect(updateAccountType(u.id, 'wizard')).rejects.toThrow(AppError);
  });

  it('throws 404 when the user does not exist', async () => {
    await expect(updateAccountType('nonexistent-id', 'official')).rejects.toThrow(AppError);
  });
});

describe('followUser / unfollowUser', () => {
  it('creates and removes a follow relationship', async () => {
    const a = await createUser('follower');
    const b = await createUser('followee');
    await followUser(a.id, b.id);
    expect(
      await prisma.follow.findUnique({ where: { followerId_followingId: { followerId: a.id, followingId: b.id } } }),
    ).not.toBeNull();

    await unfollowUser(a.id, b.id);
    expect(
      await prisma.follow.findUnique({ where: { followerId_followingId: { followerId: a.id, followingId: b.id } } }),
    ).toBeNull();
  });

  it('throws 400 on self-follow', async () => {
    const a = await createUser('selfie');
    await expect(followUser(a.id, a.id)).rejects.toThrow(AppError);
  });

  it('throws 409 when already following', async () => {
    const a = await createUser('a');
    const b = await createUser('b');
    await followUser(a.id, b.id);
    await expect(followUser(a.id, b.id)).rejects.toThrow(AppError);
  });

  it('throws 404 when target does not exist', async () => {
    const a = await createUser('seeker');
    await expect(followUser(a.id, 'nonexistent')).rejects.toThrow(AppError);
  });

  it('throws 404 when unfollowing a user not being followed', async () => {
    const a = await createUser('uf1');
    const b = await createUser('uf2');
    await expect(unfollowUser(a.id, b.id)).rejects.toThrow(AppError);
  });
});

describe('getFeed', () => {
  it('returns posts from followed users only', async () => {
    const a = await createUser('feeder');
    const b = await createUser('source');
    const c = await createUser('outsider');

    await prisma.post.create({ data: { userId: b.id, content: 'Followed post' } });
    await prisma.post.create({ data: { userId: c.id, content: 'Not in feed' } });
    await followUser(a.id, b.id);

    const feed = await getFeed(a.id, page);
    expect(feed).toHaveLength(1);
    expect(feed[0]!.content).toBe('Followed post');
    expect(feed[0]!.user.name).toBe('source');
  });

  it('amplifies a followed account\'s repost into the feed with a reposter label', async () => {
    const viewer = await createUser('viewer');
    const amplifier = await createUser('amplifier');
    const stranger = await createUser('stranger');

    // The original post is authored by someone the viewer does NOT follow.
    const post = await prisma.post.create({ data: { userId: stranger.id, content: 'unfollowed original' } });
    await followUser(viewer.id, amplifier.id);
    await prisma.repost.create({ data: { userId: amplifier.id, postId: post.id } });

    const feed = await getFeed(viewer.id, page);
    expect(feed).toHaveLength(1);
    expect(feed[0]!.id).toBe(post.id);
    expect(feed[0]!.reposter?.id).toBe(amplifier.id);
  });
});

describe('getUserPosts', () => {
  it('includes the user\'s own reposts alongside their authored posts', async () => {
    const user = await createUser('mixer');
    const other = await createUser('author');
    const own = await prisma.post.create({ data: { userId: user.id, content: 'my own post' } });
    const external = await prisma.post.create({ data: { userId: other.id, content: 'someone else' } });
    await prisma.repost.create({ data: { userId: user.id, postId: external.id } });

    const timeline = await getUserPosts(user.id, page);
    const byId = new Map(timeline.map((p) => [p.id, p]));
    expect(byId.get(own.id)!.reposter ?? null).toBeNull();
    expect(byId.get(external.id)!.reposter?.id).toBe(user.id);
  });
});
