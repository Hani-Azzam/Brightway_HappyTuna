import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';

export function LoginDialog({ onClose }: { onClose: () => void }) {
  const { login } = useAuth();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await login(name.trim());
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <form className="dialog" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="fish">🐟</div>
        <h2>Join the conversation</h2>
        <p>No passwords here — just pick a name to post, like, and follow. A new name is created instantly.</p>
        <input
          autoFocus
          placeholder="Your name"
          value={name}
          maxLength={50}
          onChange={(e) => setName(e.target.value)}
        />
        {error && <p className="error-text">{error}</p>}
        <button className="btn-primary" type="submit" disabled={busy || !name.trim()}>
          Continue
        </button>
        <button type="button" className="dismiss" onClick={onClose}>
          Keep browsing as a guest
        </button>
      </form>
    </div>
  );
}
