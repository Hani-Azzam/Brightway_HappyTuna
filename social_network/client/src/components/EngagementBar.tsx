import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Post } from '../types';

export function EngagementBar({
  post,
  onQuote,
  onAuthRequired,
}: {
  post: Post;
  onQuote: (post: Post) => void;
  onAuthRequired: () => void;
}) {
  const { session } = useAuth();
  const [liked, setLiked] = useState(post.viewerHasLiked ?? false);
  const [reposted, setReposted] = useState(post.viewerHasReposted ?? false);
  const [likes, setLikes] = useState(post._count.likes);
  const [reposts, setReposts] = useState(post._count.reposts);

  function requireAuth(): boolean {
    if (!session) {
      onAuthRequired();
      return false;
    }
    return true;
  }

  async function toggleLike(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!requireAuth()) return;
    const next = !liked;
    setLiked(next);
    setLikes((c) => c + (next ? 1 : -1));
    try {
      if (next) await api.like(post.id);
      else await api.unlike(post.id);
    } catch {
      /* keep optimistic state */
    }
  }

  async function toggleRepost(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!requireAuth()) return;
    const next = !reposted;
    setReposted(next);
    setReposts((c) => c + (next ? 1 : -1));
    try {
      if (next) await api.repost(post.id);
      else await api.unrepost(post.id);
    } catch {
      /* keep optimistic state */
    }
  }

  function quote(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!requireAuth()) return;
    onQuote(post);
  }

  return (
    <div className="actions">
      <Link className="action" to={`/post/${post.id}`} onClick={(e) => e.stopPropagation()} title="Reply" aria-label="Reply">
        💬 <span>{post._count.comments}</span>
      </Link>
      <button className={`action repost ${reposted ? 'on' : ''}`} onClick={toggleRepost} title="Repost" aria-pressed={reposted}>
        ⟲ <span>{reposts}</span>
      </button>
      <button className={`action like ${liked ? 'on' : ''}`} onClick={toggleLike} title="Like" aria-pressed={liked}>
        ♥ <span>{likes}</span>
      </button>
      <button className="action" onClick={quote} title="Quote post" aria-label="Quote post">
        ❝
      </button>
    </div>
  );
}
