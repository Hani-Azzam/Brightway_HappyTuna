import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { Avatar } from '../components/Avatar';
import { AccountBadge } from '../components/AccountBadge';
import { PostContent } from '../components/PostContent';
import { QuoteCard } from '../components/QuoteCard';
import { EngagementBar } from '../components/EngagementBar';
import { useAuth } from '../auth/AuthContext';
import { useShell } from '../components/shellContext';
import { relativeTime } from '../utils/time';
import type { Comment, Post } from '../types';

export function PostPage() {
  const { id = '' } = useParams();
  const { session } = useAuth();
  const { onQuote, onAuthRequired } = useShell();
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    setPost(null);
    setError(null);
    api
      .getPost(id)
      .then((p) => {
        if (!active) return;
        setPost(p);
        setComments(p.comments);
      })
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [id]);

  async function submitReply() {
    if (!session) {
      onAuthRequired();
      return;
    }
    if (!text.trim()) return;
    setBusy(true);
    try {
      const comment = await api.addComment(id, text.trim());
      setComments((prev) => [...prev, comment]);
      setText('');
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <div className="empty">
        <span className="big">⚠️</span>
        {error}
      </div>
    );
  }
  if (!post) return <div className="loading">Loading…</div>;

  return (
    <>
      <header className="sticky-head">
        <h1 className="head-title">Post</h1>
      </header>

      <div className="detail-author">
        <Avatar avatar={post.user.avatar} accountType={post.user.accountType} size={48} />
        <div>
          <Link className="name" to={`/user/${post.user.id}`} style={{ fontWeight: 700 }}>
            {post.user.name}
          </Link>{' '}
          <AccountBadge accountType={post.user.accountType} />
          <div className="profile-handle">@{post.user.name}</div>
        </div>
      </div>

      <div className="detail-content">
        <PostContent text={post.content} />
        {post.repostOf && <QuoteCard post={post.repostOf} />}
      </div>

      <div className="detail-stats">
        <span>
          <b>{post._count.reposts}</b> Reposts
        </span>
        <span>
          <b>{post._count.likes}</b> Likes
        </span>
        <span>{relativeTime(post.createdAt)} ago</span>
      </div>

      <div style={{ padding: '4px 16px', borderBottom: '1px solid var(--hairline)' }}>
        <EngagementBar post={post} onQuote={onQuote} onAuthRequired={onAuthRequired} />
      </div>

      <div className="compose" style={{ borderBottom: '1px solid var(--hairline)' }}>
        <Avatar avatar={session?.user.avatar ?? null} accountType={session?.user.accountType} />
        <div>
          <textarea
            placeholder="Post your reply…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            style={{ minHeight: 44, fontSize: 17 }}
          />
          <div className="row">
            <span />
            <button className="btn-primary" disabled={busy || !text.trim()} onClick={submitReply}>
              Reply
            </button>
          </div>
        </div>
      </div>

      <div className="feed">
        {comments.map((c) => (
          <article key={c.id} className="post" style={{ cursor: 'default' }}>
            <Avatar avatar={c.user.avatar} accountType={c.user.accountType} />
            <div className="body">
              <div className="post-meta">
                <Link className="name" to={`/user/${c.user.id}`}>
                  {c.user.name}
                </Link>
                <AccountBadge accountType={c.user.accountType} />
                <span className="handle">@{c.user.name}</span>
                <span className="dot">·</span>
                <span className="time">{relativeTime(c.createdAt)}</span>
              </div>
              <p className="post-content">{c.content}</p>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
