import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../../server';

const app = createApp();
const prisma = new PrismaClient();

let token: string;

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();

  const res = await request(app).post('/api/auth/login').send({ name: 'tagger' });
  token = res.body.data.token;

  await request(app).post('/api/posts').set({ Authorization: `Bearer ${token}` }).send({ content: 'one #brightway' });
  await request(app).post('/api/posts').set({ Authorization: `Bearer ${token}` }).send({ content: 'two #brightway #ocean' });
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('GET /api/hashtags/trending', () => {
  it('returns trending tags with counts', async () => {
    const res = await request(app).get('/api/hashtags/trending');
    expect(res.status).toBe(200);
    const brightway = res.body.data.trending.find((t: { tag: string }) => t.tag === 'brightway');
    expect(brightway.count).toBe(2);
  });
});

describe('GET /api/hashtags/:tag', () => {
  it('returns posts for a tag (case-insensitive)', async () => {
    const res = await request(app).get('/api/hashtags/BrightWay');
    expect(res.status).toBe(200);
    expect(res.body.data.tag).toBe('brightway');
    expect(res.body.data.posts).toHaveLength(2);
  });

  it('returns an empty list for an unused tag', async () => {
    const res = await request(app).get('/api/hashtags/nothinghere');
    expect(res.status).toBe(200);
    expect(res.body.data.posts).toEqual([]);
  });
});
