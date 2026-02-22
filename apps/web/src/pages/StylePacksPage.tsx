import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { analyzeStylePack, createStylePack, listStylePacks } from '../lib';
import type { StylePack } from '../types';

export function StylePacksPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');

  const packsQuery = useQuery({ queryKey: ['style-packs'], queryFn: listStylePacks });

  const createMutation = useMutation({
    mutationFn: () => createStylePack(name, files),
    onSuccess: (pack) => {
      setName('');
      setFiles([]);
      setSelectedId(pack.id);
      void queryClient.invalidateQueries({ queryKey: ['style-packs'] });
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: (id: string) => analyzeStylePack(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['style-packs'] }),
  });

  const selectedPack = useMemo<StylePack | undefined>(
    () => packsQuery.data?.find((pack) => pack.id === selectedId) ?? packsQuery.data?.[0],
    [packsQuery.data, selectedId],
  );

  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
        <h2 className="text-xl font-semibold">Create Style Pack</h2>
        <input
          className="mt-3 w-full rounded bg-slate-800 p-2"
          placeholder="Style pack name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <input
          className="mt-3 w-full rounded bg-slate-800 p-2"
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
        />
        <button
          className="mt-3 rounded bg-indigo-500 px-4 py-2"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
        >
          {createMutation.isPending ? 'Creating...' : 'Create Pack'}
        </button>
        {createMutation.error && <p className="mt-2 text-sm text-rose-400">{createMutation.error.message}</p>}
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4">
        <h2 className="text-xl font-semibold">Style Packs</h2>
        <div className="mt-3 space-y-2">
          {packsQuery.data?.map((pack) => (
            <button
              key={pack.id}
              className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-left"
              onClick={() => setSelectedId(pack.id)}
            >
              <div className="font-medium">{pack.name}</div>
              <div className="text-xs text-slate-400">{pack.style_images.length} images</div>
              <div className="mt-2 flex flex-wrap gap-1 text-xs text-slate-400">
                {pack.style_images.slice(0, 4).map((img) => (
                  <span key={img.asset_id} className="rounded bg-slate-700 px-2 py-1">{img.path.split('/').pop()}</span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>

      {selectedPack && (
        <div className="md:col-span-2 rounded-lg border border-slate-700 bg-slate-900 p-4">
          <h3 className="text-lg font-semibold">Pack Details: {selectedPack.name}</h3>
          <button
            className="mt-3 rounded bg-emerald-600 px-3 py-2"
            onClick={() => analyzeMutation.mutate(selectedPack.id)}
            disabled={analyzeMutation.isPending}
          >
            {analyzeMutation.isPending ? 'Analyzing...' : 'Analyze style pack'}
          </button>
          <pre className="mt-3 overflow-auto rounded bg-slate-950 p-3 text-xs text-emerald-300">
            {JSON.stringify(selectedPack.constraints, null, 2)}
          </pre>
        </div>
      )}
    </section>
  );
}
