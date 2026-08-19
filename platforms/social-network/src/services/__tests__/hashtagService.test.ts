import { PrismaClient } from '@prisma/client';
import { createPost } from '../postService';
import { getPostsByHashtag, getTrending } from '../hashtagService';

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

describe('getPostsByHashtag', () => {
  it('returns posts carrying the tag (case-insensitive, # optional)', async () => {
    const u = await createUser('tagger');
    await createPost(u.id, 'Loving #BrightWay tuna');
    await createPost(u.id, 'More #brightway and #ocean');
    await createPost(u.id, 'Unrelated post');

    expect(await getPostsByHashtag('brightway', page)).toHaveLength(2);
    expect(await getPostsByHashtag('#BrightWay', page)).toHaveLength(2);
    expect(await getPostsByHashtag('ocean', page)).toHaveLength(1);
  });
});

describe('getTrending', () => {
  it('ranks hashtags by usage count', async () => {
    const u = await createUser('trender');
    await createPost(u.id, 'one #brightway');
    await createPost(u.id, 'two #brightway #ocean');
    await createPost(u.id, 'three #ocean');

    const trending = await getTrending();
    expect(trending.find((t) => t.tag === 'brightway')?.count).toBe(2);
    expect(trending.find((t) => t.tag === 'ocean')?.count).toBe(2);
    // highest-first ordering
    expect(trending[0]!.count).toBeGreaterThanOrEqual(trending[trending.length - 1]!.count);
  });

  it('returns an empty array when there are no tagged posts', async () => {
    expect(await getTrending()).toEqual([]);
  });
});
