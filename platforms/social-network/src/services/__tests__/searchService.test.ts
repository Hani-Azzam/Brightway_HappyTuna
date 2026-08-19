import { PrismaClient } from '@prisma/client';
import { createPost } from '../postService';
import { search } from '../searchService';
import { AppError } from '../../utils/errors';

const prisma = new PrismaClient();
const page = { skip: 0, take: 20 };

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

describe('search', () => {
  it('matches users by name, posts by content, and hashtags by tag (case-insensitive)', async () => {
    const sam = await createUser('searchable_sam');
    await createPost(sam.id, 'A post about BrightWay and #ocean');

    const byContent = await search('bright', page);
    expect(byContent.posts.length).toBeGreaterThan(0);

    const byUser = await search('searchable', page);
    expect(byUser.users).toHaveLength(1);

    const byTag = await search('#ocean', page);
    expect(byTag.hashtags).toHaveLength(1);
  });

  it('throws 400 when the query is empty', async () => {
    await expect(search('   ', page)).rejects.toThrow(AppError);
  });
});
