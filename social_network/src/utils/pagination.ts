/**
 * Pagination primitives shared by list/feed endpoints.
 */
export interface Pagination {
  skip: number;
  take: number;
}

/**
 * Parses `page` (1-based) and `limit` query params into Prisma `skip`/`take`.
 * Defaults to page 1 with `defaultTake` items and clamps `limit` to `[1, maxTake]`.
 * Invalid/non-numeric values fall back to the defaults.
 */
export function parsePagination(
  query: Record<string, unknown>,
  defaultTake = 20,
  maxTake = 100,
): Pagination {
  const pageRaw = parseInt(String(query['page'] ?? '1'), 10);
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : 1;

  const limitRaw = parseInt(String(query['limit'] ?? String(defaultTake)), 10);
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : defaultTake;
  const take = Math.min(limit, maxTake);

  return { skip: (page - 1) * take, take };
}
