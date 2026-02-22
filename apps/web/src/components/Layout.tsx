import { NavLink, Outlet } from 'react-router-dom';

const links = [
  { to: '/', label: 'Style Packs' },
  { to: '/translate', label: 'Translate' },
  { to: '/history', label: 'History' },
];

export function Layout() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl p-6 text-slate-100">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Style Translator</h1>
        <nav className="flex gap-2">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `rounded px-4 py-2 text-sm ${isActive ? 'bg-indigo-500 text-white' : 'bg-slate-800 text-slate-200'}`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <Outlet />
    </main>
  );
}
