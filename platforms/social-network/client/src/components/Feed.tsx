import { PostCard } from './PostCard';
import type { Post } from '../types';

export function Feed({
  posts,
  error,
  emptyText,
  onQuote,
  onAuthRequired,
}: {
  posts: Post[] | null;
  error?: string | null;
  emptyText: string;
  onQuote: (post: Post) => void;
  onAuthRequired: () => void;
}) {
  if (error) {
    return (
      <div className="empty">
        <span className="big">⚠️</span>
        {error}
      </div>
    );
  }
  if (posts === null) return <div className="loading">Loading…</div>;
  if (posts.length === 0) {
    return (
      <div className="empty">
        <span className="big">🌊</span>
        {emptyText}
      </div>
    );
  }
  return (
    <div className="feed">
      {posts.map((post) => (
        <PostCard key={post.id} post={post} onQuote={onQuote} onAuthRequired={onAuthRequired} />
      ))}
    </div>
  );
}
