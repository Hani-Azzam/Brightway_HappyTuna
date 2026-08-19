import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../../server';

const app = createApp();
const prisma = new PrismaClient();

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();

  const login = await request(app).post('/api/auth/login').send({ name: 'searchable_sam' });
  const token = login.body.data.token;
  await request(app).post('/api/posts').set({ Authorization: `Bearer ${token}` }).send({ content: 'About BrightWay and #ocean' });
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('GET /api/search', () => {
  it('returns matching users, posts, and hashtags', async () => {
    const res = await request(app).get('/api/search').query({ q: 'bright' });
    expect(res.status).toBe(200);
    expect(res.body.data.posts.length).toBeGreaterThan(0);

    const userRes = await request(app).get('/api/search').query({ q: 'searchable' });
    expect(userRes.body.data.users).toHaveLength(1);

    const tagRes = await request(app).get('/api/search').query({ q: '#ocean' });
    expect(tagRes.body.data.hashtags).toHaveLength(1);
  });

  it('returns 400 when q is missing', async () => {
    const res = await request(app).get('/api/search');
    expect(res.status).toBe(400);
  });
});
