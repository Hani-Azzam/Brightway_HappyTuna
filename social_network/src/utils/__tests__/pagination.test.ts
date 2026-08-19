import { parsePagination } from '../pagination';

describe('parsePagination', () => {
  it('defaults to page 1 / take 20', () => {
    expect(parsePagination({})).toEqual({ skip: 0, take: 20 });
  });

  it('computes skip from page and limit', () => {
    expect(parsePagination({ page: '3', limit: '10' })).toEqual({ skip: 20, take: 10 });
  });

  it('clamps limit to maxTake', () => {
    expect(parsePagination({ limit: '1000' }, 20, 100)).toEqual({ skip: 0, take: 100 });
  });

  it('falls back to defaults on invalid input', () => {
    expect(parsePagination({ page: 'abc', limit: '-5' })).toEqual({ skip: 0, take: 20 });
  });
});
