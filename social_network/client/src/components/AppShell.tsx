import { Outlet } from 'react-router-dom';
import { LeftNav } from './LeftNav';
import { RightRail } from './RightRail';
import type { ShellContext } from './shellContext';

export function AppShell({
  onCompose,
  onLogin,
  onAuthRequired,
  context,
}: {
  onCompose: () => void;
  onLogin: () => void;
  onAuthRequired: () => void;
  context: ShellContext;
}) {
  return (
    <div className="shell">
      <LeftNav onCompose={onCompose} onLogin={onLogin} />
      <main className="center">
        <Outlet context={context} />
      </main>
      <RightRail onAuthRequired={onAuthRequired} />
    </div>
  );
}
