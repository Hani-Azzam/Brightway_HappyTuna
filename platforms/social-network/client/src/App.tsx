import { lazy, Suspense, useState } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { ComposeModal } from './components/ComposeModal';
import { LoginDialog } from './components/LoginDialog';
import { HomePage } from './pages/HomePage';
import { ExplorePage } from './pages/ExplorePage';
import { ProfilePage } from './pages/ProfilePage';
import { PostPage } from './pages/PostPage';
import { HashtagPage } from './pages/HashtagPage';
import { NotFound } from './pages/Misc';
import type { ShellContext } from './components/shellContext';

// Lazy-loaded so Recharts only ships when a researcher opens the dashboard.
const DashboardPage = lazy(() => import('./dashboard/DashboardPage').then((m) => ({ default: m.DashboardPage })));
import type { Post } from './types';

export default function App() {
  const navigate = useNavigate();
  const [loginOpen, setLoginOpen] = useState(false);
  const [compose, setCompose] = useState<{ open: boolean; quoting: Post | null }>({ open: false, quoting: null });

  const onAuthRequired = () => setLoginOpen(true);
  const onQuote = (post: Post) => setCompose({ open: true, quoting: post });
  const context: ShellContext = { onAuthRequired, onQuote };

  return (
    <>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <Suspense fallback={<div className="dash"><div className="dempty" style={{ padding: 80 }}>Loading dashboard…</div></div>}>
              <DashboardPage />
            </Suspense>
          }
        />
        <Route
          element={
            <AppShell
              onCompose={() => setCompose({ open: true, quoting: null })}
              onLogin={() => setLoginOpen(true)}
              onAuthRequired={onAuthRequired}
              context={context}
            />
          }
        >
          <Route index element={<HomePage />} />
          <Route path="explore" element={<ExplorePage />} />
          <Route path="hashtag/:tag" element={<HashtagPage />} />
          <Route path="user/:id" element={<ProfilePage />} />
          <Route path="post/:id" element={<PostPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>

      {compose.open && (
        <ComposeModal
          quoting={compose.quoting}
          onClose={() => setCompose({ open: false, quoting: null })}
          onPosted={(post) => {
            setCompose({ open: false, quoting: null });
            navigate(`/post/${post.id}`);
          }}
          onAuthRequired={onAuthRequired}
        />
      )}
      {loginOpen && <LoginDialog onClose={() => setLoginOpen(false)} />}
    </>
  );
}
