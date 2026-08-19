import { Link } from 'react-router-dom';
import { AccountBadge } from './AccountBadge';
import type { Post } from '../types';

/** Compact embedded preview of a quoted (reposted-with-comment) post. */
export function QuoteCard({ post }: { post: Post }) {
  return (
    <Link className="quote" to={`/post/${post.id}`} onClick={(e) => e.stopPropagation()} style={{ display: 'block' }}>
      <div className="post-meta">
        <span className="name">{post.user.name}</span>
        <AccountBadge accountType={post.user.accountType} />
        <span className="handle">@{post.user.name}</span>
      </div>
      <p className="post-content">{post.content}</p>
    </Link>
  );
}
