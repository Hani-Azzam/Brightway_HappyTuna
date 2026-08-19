import { PrismaClient } from '@prisma/client';
import { createComment, getCommentsByPost } from '../commentService';
import { AppError } from '../../utils/errors';

const prisma = new PrismaClient();

function createUser(name: string) {
  return prisma.user.create({ data: { name } });
}

function createPost(userId: string, content: string) {
  return prisma.post.create({ data: { userId, content } });
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.user.deleteMany();
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('createComment', () => {
  it('creates a comment and returns it with author info', async () => {
    const u = await createUser('commenter');
    const post = await createPost(u.id, 'A post');
    const comment = await createComment(post.id, u.id, 'Nice post!');
    expect(comment.content).toBe('Nice post!');
    expect(comment.user.name).toBe('commenter');
  });

  it('throws 400 on empty content', async () => {
    const u = await createUser('emptyc');
    const post = await createPost(u.id, 'Post');
    await expect(createComment(post.id, u.id, '  ')).rejects.toThrow(AppError);
  });

  it('throws 404 when the post does not exist', async () => {
    const u = await createUser('ghostc');
    await expect(createComment('nonexistent-post', u.id, 'Hi')).rejects.toThrow(AppError);
  });

  it('throws 400 when the comment exceeds 280 chars', async () => {
    const u = await createUser('longc');
    const post = await createPost(u.id, 'Post');
    await expect(createComment(post.id, u.id, 'a'.repeat(281))).rejects.toThrow(AppError);
  });
});

describe('getCommentsByPost', () => {
  it('returns comments in chronological order', async () => {
    const u = await createUser('ordered');
    const post = await createPost(u.id, 'Post');
    await createComment(post.id, u.id, 'First');
    await createComment(post.id, u.id, 'Second');
    const comments = await getCommentsByPost(post.id);
    expect(comments[0]!.content).toBe('First');
    expect(comments[1]!.content).toBe('Second');
  });

  it('throws 404 for a non-existent post', async () => {
    await expect(getCommentsByPost('bad-id')).rejects.toThrow(AppError);
  });
});
