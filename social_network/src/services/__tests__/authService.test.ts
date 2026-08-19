import { PrismaClient } from '@prisma/client';
import { login } from '../authService';
import { AppError } from '../../utils/errors';

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

describe('login (name-only)', () => {
  it('creates a new user on first login and returns token = user id', async () => {
    const { token, user } = await login('alice');
    expect(user.name).toBe('alice');
    expect(token).toBe(user.id);
    expect(user.accountType).toBe('regular');
  });

  it('reuses the existing user for a returning name (no duplicates)', async () => {
    const first = await login('bob');
    const second = await login('bob');
    expect(second.user.id).toBe(first.user.id);
    expect(await prisma.user.count({ where: { name: 'bob' } })).toBe(1);
  });

  it('trims surrounding whitespace', async () => {
    const { user } = await login('  carol  ');
    expect(user.name).toBe('carol');
  });

  it('throws 400 on empty name', async () => {
    await expect(login('   ')).rejects.toThrow(AppError);
  });

  it('throws 400 when name exceeds 50 characters', async () => {
    await expect(login('a'.repeat(51))).rejects.toThrow(AppError);
  });
});
