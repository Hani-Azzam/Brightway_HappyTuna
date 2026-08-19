import request from 'supertest';
import { createApp } from '../../server';

const app = createApp();

describe('GET /api/meta', () => {
  it('returns the platform and company branding', async () => {
    const res = await request(app).get('/api/meta');
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(typeof res.body.data.platformName).toBe('string');
    expect(res.body.data.platformName.length).toBeGreaterThan(0);
    expect(typeof res.body.data.companyName).toBe('string');
    expect(res.body.data.companyName.length).toBeGreaterThan(0);
  });
});
