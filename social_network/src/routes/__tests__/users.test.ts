import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../../server';

const app = createApp();
const prisma = new PrismaClient();

let tokenA: string;
let userAId: string;
let userBId: string;

async function loginAs(name: string): Promise<{ token: string; user: { id: string } }> {
  const res = await request(app).post('/api/auth/login').send({ name });
  return res.body.data;
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.user.deleteMany();

  const a = await loginAs('user_a');
  tokenA = a.token;
  userAId = a.user.id;
  const b = await loginAs('user_b');
  userBId = b.user.id;
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('GET /api/users', () => {
  it('returns the list of users', async () => {
    const res = await request(app).get('/api/users');
    expect(res.status).toBe(200);
    expect(res.body.data.users).toHaveLength(2);
  });
});

describe('GET /api/users/:id', () => {
  it('returns a user profile', async () => {
    const res = await request(app).get(`/api/users/${userAId}`);
    expect(res.status).toBe(200);
    expect(res.body.data.user.name).toBe('user_a');
  });

  it('returns 404 for an unknown user', async () => {
    const res = await request(app).get('/api/users/nonexistent');
    expect(res.status).toBe(404);
  });
});

describe('PATCH /api/users/:id', () => {
  it('lets a user set their own account type', async () => {
    const res = await request(app)
      .patch(`/api/users/${userAId}`)
      .set('Authorization', `Bearer ${tokenA}`)
      .send({ accountType: 'journalist' });
    expect(res.status).toBe(200);
    expect(res.body.data.user.accountType).toBe('journalist');
  });

  it('rejects an invalid account type', async () => {
    const res = await request(app)
      .patch(`/api/users/${userAId}`)
      .set('Authorization', `Bearer ${tokenA}`)
      .send({ accountType: 'wizard' });
    expect(res.status).toBe(400);
  });

  it('returns 403 when modifying another user', async () => {
    const res = await request(app)
      .patch(`/api/users/${userBId}`)
      .set('Authorization', `Bearer ${tokenA}`)
      .send({ accountType: 'official' });
    expect(res.status).toBe(403);
  });

  it('returns 401 without auth', async () => {
    const res = await request(app).patch(`/api/users/${userAId}`).send({ accountType: 'official' });
    expect(res.status).toBe(401);
  });
});

describe('POST /api/users/:id/follow/:targetId', () => {
  it('lets a user follow another', async () => {
    const res = await request(app)
      .post(`/api/users/${userAId}/follow/${userBId}`)
      .set('Authorization', `Bearer ${tokenA}`);
    expect(res.status).toBe(200);
  });

  it('returns 401 without auth', async () => {
    const res = await request(app).post(`/api/users/${userAId}/follow/${userBId}`);
    expect(res.status).toBe(401);
  });

  it('returns 403 when acting as another user', async () => {
    const res = await request(app)
      .post(`/api/users/${userBId}/follow/${userAId}`)
      .set('Authorization', `Bearer ${tokenA}`);
    expect(res.status).toBe(403);
  });
});

describe('DELETE /api/users/:id/follow/:targetId', () => {
  it('unfollows a user', async () => {
    await request(app)
      .post(`/api/users/${userAId}/follow/${userBId}`)
      .set('Authorization', `Bearer ${tokenA}`);

    const res = await request(app)
      .delete(`/api/users/${userAId}/follow/${userBId}`)
      .set('Authorization', `Bearer ${tokenA}`);
    expect(res.status).toBe(200);
  });
});

describe('GET /api/users/:id/feed', () => {
  it('returns the personalized feed', async () => {
    await request(app)
      .post(`/api/users/${userAId}/follow/${userBId}`)
      .set('Authorization', `Bearer ${tokenA}`);

    const b = await loginAs('user_b');
    await request(app)
      .post('/api/posts')
      .set('Authorization', `Bearer ${b.token}`)
      .send({ content: 'From user B' });

    const res = await request(app)
      .get(`/api/users/${userAId}/feed`)
      .set('Authorization', `Bearer ${tokenA}`);
    expect(res.status).toBe(200);
    expect(res.body.data.posts).toHaveLength(1);
  });

  it('returns 401 without auth', async () => {
    const res = await request(app).get(`/api/users/${userAId}/feed`);
    expect(res.status).toBe(401);
  });

  it("returns 403 for another user's feed", async () => {
    const res = await request(app)
      .get(`/api/users/${userBId}/feed`)
      .set('Authorization', `Bearer ${tokenA}`);
    expect(res.status).toBe(403);
  });
});

describe('GET /api/users/:id/posts', () => {
  it("returns the user's own posts", async () => {
    await request(app).post('/api/posts').set('Authorization', `Bearer ${tokenA}`).send({ content: 'my own post' });
    const res = await request(app).get(`/api/users/${userAId}/posts`);
    expect(res.status).toBe(200);
    expect(res.body.data.posts).toHaveLength(1);
    expect(res.body.data.posts[0].content).toBe('my own post');
  });
});

describe('GET /api/users/:id/following', () => {
  it('lists accounts the user follows', async () => {
    await request(app).post(`/api/users/${userAId}/follow/${userBId}`).set('Authorization', `Bearer ${tokenA}`);
    const res = await request(app).get(`/api/users/${userAId}/following`);
    expect(res.status).toBe(200);
    expect(res.body.data.users).toHaveLength(1);
    expect(res.body.data.users[0].id).toBe(userBId);
  });
});
