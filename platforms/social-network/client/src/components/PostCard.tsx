import { Link, useNavigate } from 'react-router-dom';
import { Avatar } from './Avatar';
import { AccountBadge } from './AccountBadge';
import { PostContent } from './PostContent';
import { QuoteCard } from './QuoteCard';
import { EngagementBar } from './EngagementBar';
import { relativeTime } from '../utils/time';
import type { Post } from '../types';

export function PostCard({
  post,
  onQuote,
  onAuthRequired,
}: {
  post: Post;
  onQuote: (post: Post) => void;
  onAuthRequired: () => void;
}) {
  const navigate = useNavigate();

  return (
    <article className="post" onClick={() => navigate(`/post/${post.id}`)}>
      <Avatar avatar={post.user.avatar} accountType={post.user.accountType} />
      <div className="body">
        {post.reposter && (
          <div className="repost-flag">
            <span aria-hidden="true">⟲</span>
            <Link className="name" to={`/user/${post.reposter.id}`} onClick={(e) => e.stopPropagation()}>
              {post.reposter.name}
            </Link>
            <span>reposted</span>
          </div>
        )}
        <div className="post-meta">
          <Link className="name" to={`/user/${post.user.id}`} onClick={(e) => e.stopPropagation()}>
            {post.user.name}
          </Link>
          <AccountBadge accountType={post.user.accountType} />
          <span className="handle">@{post.user.name}</span>
          <span className="dot">·</span>
          <span className="time">{relativeTime(post.createdAt)}</span>
        </div>
        <p className="post-content">
          <PostContent text={post.content} />
        </p>
        {post.repostOf && <QuoteCard post={post.repostOf} />}
        <EngagementBar post={post} onQuote={onQuote} onAuthRequired={onAuthRequired} />
      </div>
    </article>
  );
}
