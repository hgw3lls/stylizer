import type { StylePack } from '../types';

type Props = {
  title: string;
  pack: StylePack;
};

export function StylePackCard({ title, pack }: Props) {
  return (
    <article className="rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-lg">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-slate-400">
        {pack.source} → {pack.target}
      </p>
      <pre className="mt-3 overflow-auto rounded bg-slate-950 p-3 text-xs text-emerald-300">
        {JSON.stringify(pack, null, 2)}
      </pre>
    </article>
  );
}
