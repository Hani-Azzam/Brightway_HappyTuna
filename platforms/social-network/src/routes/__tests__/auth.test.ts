import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../../server';

const app = createApp();
const prisma = new PrismaClient();

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.user.deleteMany();
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('POST /api/auth/login', () => {
  it('creates a user on first login and returns token + user', async () => {
    const res = await request(app).post('/api/auth/login').send({ name: 'newuser' });
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.user.name).toBe('newuser');
    expect(res.body.data.token).toBe(res.body.data.user.id);
  });

  it('returns the same user for a returning name', async () => {
    const first = await request(app).post('/api/auth/login').send({ name: 'repeat' });
    const second = await request(app).post('/api/auth/login').send({ name: 'repeat' });
    expect(second.body.data.user.id).toBe(first.body.data.user.id);
  });

  it('returns 400 when name is missing', async () => {
    const res = await request(app).post('/api/auth/login').send({});
    expect(res.status).toBe(400);
    expect(res.body.success).toBe(false);
  });
});
