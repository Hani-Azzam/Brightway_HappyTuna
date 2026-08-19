import { PrismaClient } from '@prisma/client';
import { likePost, unlikePost, repostPost, unrepostPost } from '../engagementService';
import { createPost } from '../postService';
import { AppError } from '../../utils/errors';

const prisma = new PrismaClient();

function createUser(name: string) {
  return prisma.user.create({ data: { name } });
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('likePost / unlikePost', () => {
  it('likes then unlikes a post', async () => {
    const a = await createUser('liker');
    const b = await createUser('author');
    const post = await createPost(b.id, 'Like me');

    await likePost(a.id, post.id);
    expect(
      await prisma.like.findUnique({ where: { userId_postId: { userId: a.id, postId: post.id } } }),
    ).not.toBeNull();

    await unlikePost(a.id, post.id);
    expect(
      await prisma.like.findUnique({ where: { userId_postId: { userId: a.id, postId: post.id } } }),
    ).toBeNull();
  });

  it('throws 409 when already liked', async () => {
    const a = await createUser('dup');
    const post = await createPost(a.id, 'Post');
    await likePost(a.id, post.id);
    await expect(likePost(a.id, post.id)).rejects.toThrow(AppError);
  });

  it('throws 404 when liking a missing post', async () => {
    const a = await createUser('ghost');
    await expect(likePost(a.id, 'nonexistent')).rejects.toThrow(AppError);
  });

  it('throws 404 when unliking a post that was not liked', async () => {
    const a = await createUser('nl');
    const post = await createPost(a.id, 'Post');
    await expect(unlikePost(a.id, post.id)).rejects.toThrow(AppError);
  });
});

describe('repostPost / unrepostPost', () => {
  it('reposts then unreposts a post', async () => {
    const a = await createUser('reposter');
    const b = await createUser('src');
    const post = await createPost(b.id, 'Amplify me');

    await repostPost(a.id, post.id);
    expect(
      await prisma.repost.findUnique({ where: { userId_postId: { userId: a.id, postId: post.id } } }),
    ).not.toBeNull();

    await unrepostPost(a.id, post.id);
    expect(
      await prisma.repost.findUnique({ where: { userId_postId: { userId: a.id, postId: post.id } } }),
    ).toBeNull();
  });

  it('throws 409 when already reposted', async () => {
    const a = await createUser('rdup');
    const post = await createPost(a.id, 'Post');
    await repostPost(a.id, post.id);
    await expect(repostPost(a.id, post.id)).rejects.toThrow(AppError);
  });

  it('throws 404 when reposting a missing post', async () => {
    const a = await createUser('rghost');
    await expect(repostPost(a.id, 'nonexistent')).rejects.toThrow(AppError);
  });

  it('throws 404 when unreposting a post that was not reposted', async () => {
    const a = await createUser('rnl');
    const post = await createPost(a.id, 'Post');
    await expect(unrepostPost(a.id, post.id)).rejects.toThrow(AppError);
  });
});
