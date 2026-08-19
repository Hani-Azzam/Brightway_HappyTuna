import type {
  AccountType,
  AnalysisConfig,
  AspectStat,
  CohortReport,
  Comment,
  Engine,
  Meta,
  Influencer,
  Narrative,
  Overview,
  Post,
  SearchResults,
  Session,
  Spike,
  TimelineBucket,
  TopPost,
  TrendingTag,
  TrendStat,
  UserSummary,
  UserWithCounts,
} from '../types';

const SESSION_KEY = 'brightway.session';

export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session | null): void {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
}

interface Envelope<T> {
  success: boolean;
  data?: T;
  error?: string;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  const session = loadSession();
  if (options.auth && session) headers['Authorization'] = `Bearer ${session.token}`;

  const res = await fetch(`/api${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const json = (await res.json().catch(() => ({ success: false, error: `HTTP ${res.status}` }))) as Envelope<T>;
  if (!json.success) throw new Error(json.error || `Request failed (${res.status})`);
  return json.data as T;
}

export const api = {
  getMeta: () => request<Meta>('/meta'),
  login: (name: string) => request<Session>('/auth/login', { method: 'POST', body: { name } }),

  getGlobalFeed: (page = 1) => request<{ posts: Post[] }>(`/posts?page=${page}&limit=30`).then((d) => d.posts),
  getMyFeed: (userId: string, page = 1) =>
    request<{ posts: Post[] }>(`/users/${userId}/feed?page=${page}&limit=30`, { auth: true }).then((d) => d.posts),
  getPost: (id: string) => request<{ post: Post }>(`/posts/${id}`).then((d) => d.post),
  getComments: (id: string) => request<{ comments: Comment[] }>(`/posts/${id}/comments`).then((d) => d.comments),
  createPost: (content: string, repostOfId?: string) =>
    request<{ post: Post }>('/posts', { method: 'POST', auth: true, body: { content, repostOfId } }).then((d) => d.post),
  addComment: (id: string, content: string) =>
    request<{ comment: Comment }>(`/posts/${id}/comments`, { method: 'POST', auth: true, body: { content } }).then((d) => d.comment),
  like: (id: string) => request(`/posts/${id}/like`, { method: 'POST', auth: true }),
  unlike: (id: string) => request(`/posts/${id}/like`, { method: 'DELETE', auth: true }),
  repost: (id: string) => request(`/posts/${id}/repost`, { method: 'POST', auth: true }),
  unrepost: (id: string) => request(`/posts/${id}/repost`, { method: 'DELETE', auth: true }),

  getUsers: (page = 1) => request<{ users: UserWithCounts[] }>(`/users?page=${page}&limit=50`).then((d) => d.users),
  getUser: (id: string) => request<{ user: UserWithCounts }>(`/users/${id}`).then((d) => d.user),
  updateAccountType: (id: string, accountType: AccountType) =>
    request<{ user: UserWithCounts }>(`/users/${id}`, { method: 'PATCH', auth: true, body: { accountType } }).then((d) => d.user),
  getUserPosts: (id: string, page = 1) =>
    request<{ posts: Post[] }>(`/users/${id}/posts?page=${page}&limit=30`).then((d) => d.posts),
  getFollowing: (id: string) => request<{ users: UserSummary[] }>(`/users/${id}/following?limit=100`).then((d) => d.users),
  follow: (meId: string, targetId: string) => request(`/users/${meId}/follow/${targetId}`, { method: 'POST', auth: true }),
  unfollow: (meId: string, targetId: string) => request(`/users/${meId}/follow/${targetId}`, { method: 'DELETE', auth: true }),

  getTrending: (limit = 8) => request<{ trending: TrendingTag[] }>(`/hashtags/trending?limit=${limit}`).then((d) => d.trending),
  getHashtag: (tag: string, page = 1) =>
    request<{ tag: string; posts: Post[] }>(`/hashtags/${encodeURIComponent(tag)}?page=${page}&limit=30`),
  search: (q: string) => request<SearchResults>(`/search?q=${encodeURIComponent(q)}`),

  // --- analytics (research dashboard) ---
  getAnalyticsConfig: () => request<AnalysisConfig>('/analytics/config'),
  setAnalyticsConfig: (aiAnalysisEnabled: boolean) =>
    request<AnalysisConfig>('/analytics/config', { method: 'PUT', body: { aiAnalysisEnabled } }),
  runAnalysis: (reanalyze = false) =>
    request<{ analyzed: number; engine: Engine }>('/analytics/analyze', { method: 'POST', body: { reanalyze } }),
  getOverview: () => request<Overview>('/analytics/overview'),
  getTimeline: () => request<{ timeline: TimelineBucket[] }>('/analytics/sentiment/timeline').then((d) => d.timeline),
  getAspects: () => request<{ aspects: AspectStat[] }>('/analytics/aspects').then((d) => d.aspects),
  getAnalyticsTrends: () => request<{ trends: TrendStat[] }>('/analytics/trends').then((d) => d.trends),
  getInfluencers: () => request<{ influencers: Influencer[] }>('/analytics/influencers').then((d) => d.influencers),
  getSpikes: () => request<{ spikes: Spike[] }>('/analytics/spikes').then((d) => d.spikes),
  getTopAnalyticsPosts: () => request<{ posts: TopPost[] }>('/analytics/top-posts').then((d) => d.posts),
  getCohorts: () => request<CohortReport>('/analytics/cohorts'),
  getNarratives: () => request<{ narratives: Narrative[] }>('/analytics/narratives').then((d) => d.narratives),
};
