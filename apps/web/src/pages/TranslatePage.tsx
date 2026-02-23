import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError, createTranslateJob, extractResult, getJobStatus, listStylePacks } from '../lib';
import type { TranslateResponse } from '../types';

export function TranslatePage() {
  const packsQuery = useQuery({ queryKey: ['style-packs'], queryFn: listStylePacks });

  const [stylePackId, setStylePackId] = useState('');
  const [mode, setMode] = useState<'translate_single' | 'synthesize_multi'>('translate_single');
  const [files, setFiles] = useState<File[]>([]);
  const [variations, setVariations] = useState(1);
  const [drift, setDrift] = useState(0.2);
  const [density, setDensity] = useState(0.5);
  const [abstraction, setAbstraction] = useState(0.3);
  const [preserveComposition, setPreserveComposition] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);

  const createJobMutation = useMutation({
    mutationFn: () =>
      createTranslateJob({
        stylePackId,
        mode,
        inputImages: files,
        options: {
          size: '1024x1024',
          quality: 'high',
          variations,
          preserve_composition: preserveComposition,
          drift,
          density,
          abstraction,
          fusion_strategy: mode === 'synthesize_multi' ? 'collage' : undefined,
        },
      }),
    onSuccess: (job) => setJobId(job.job_id),
  });

  const jobQuery = useQuery({
    queryKey: ['job-status', jobId],
    queryFn: () => getJobStatus(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.status === 'completed' || query.state.data?.status === 'failed' ? false : 1200),
  });

  const result: TranslateResponse | null = jobQuery.data ? extractResult(jobQuery.data) : null;

  const selectedPack = useMemo(
    () => packsQuery.data?.find((pack) => pack.id === stylePackId),
    [packsQuery.data, stylePackId],
  );

  return (
    <section className="space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-4">
      <h2 className="text-xl font-semibold">Translate</h2>
      <select className="w-full rounded bg-slate-800 p-2" value={stylePackId} onChange={(event) => setStylePackId(event.target.value)}>
        <option value="">Select style pack</option>
        {packsQuery.data?.map((pack) => (
          <option key={pack.id} value={pack.id}>{pack.name}</option>
        ))}
      </select>

      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-sm">Mode
          <select className="mt-1 w-full rounded bg-slate-800 p-2" value={mode} onChange={(event) => setMode(event.target.value as 'translate_single' | 'synthesize_multi')}>
            <option value="translate_single">translate_single</option>
            <option value="synthesize_multi">synthesize_multi</option>
          </select>
        </label>
        <label className="text-sm">Variations ({variations})
          <input className="mt-1 w-full" type="range" min={1} max={6} value={variations} onChange={(event) => setVariations(Number(event.target.value))} />
        </label>
      </div>

      {[['drift', drift, setDrift], ['density', density, setDensity], ['abstraction', abstraction, setAbstraction]].map(([label, value, setter]) => (
        <label key={String(label)} className="text-sm">{String(label)} ({(value as number).toFixed(2)})
          <input className="mt-1 w-full" type="range" min={0} max={1} step={0.01} value={value as number} onChange={(event) => (setter as (v:number)=>void)(Number(event.target.value))} />
        </label>
      ))}

      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={preserveComposition} onChange={(event) => setPreserveComposition(event.target.checked)} />Preserve composition</label>

      <input type="file" multiple accept="image/png,image/jpeg,image/webp" className="w-full rounded bg-slate-800 p-2" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />

      {!selectedPack && <p className="text-sm text-amber-400">Select a style pack before translating.</p>}
      {mode === 'synthesize_multi' && files.length > 0 && (files.length < 2 || files.length > 10) && <p className="text-sm text-amber-400">synthesize_multi requires 2 to 10 images.</p>}

      <button className="rounded bg-indigo-500 px-4 py-2" onClick={() => createJobMutation.mutate()} disabled={createJobMutation.isPending}>
        {createJobMutation.isPending ? 'Submitting...' : 'Create job'}
      </button>
      {createJobMutation.error && <p className="text-sm text-rose-400">{createJobMutation.error.message}</p>}
      {createJobMutation.error instanceof ApiError && createJobMutation.error.status === 503 && (
        <div className="rounded border border-amber-500/50 bg-amber-900/30 p-3 text-sm text-amber-200">
          Image generation is currently unavailable for this API key/project. Set <code>OPENAI_IMAGE_MODEL</code> to an available model id or enable image models for this project.
        </div>
      )}

      {jobId && (
        <div className="rounded bg-slate-950 p-3 text-sm">
          <p>Job ID: {jobId}</p>
          <p>Status: {jobQuery.data?.status ?? 'pending'}</p>
          {jobQuery.data?.error_message && <p className="text-rose-400">{jobQuery.data.error_message}</p>}
        </div>
      )}

      {result && (
        <div className="space-y-2">
          <h3 className="font-semibold">Results</h3>
          <p className="text-xs text-slate-400">{result.prompt_used}</p>
          <div className="grid gap-3 md:grid-cols-3">
            {result.images.map((image, index) => (
              <div key={index} className="rounded border border-slate-700 bg-slate-950 p-2">
                <img src={`data:image/png;base64,${image.image_base64}`} className="w-full rounded" />
                <a className="mt-2 inline-block text-xs text-indigo-300" href={`data:image/png;base64,${image.image_base64}`} download={`output-${index + 1}.png`}>Download</a>
                {image.fusion_plan && <pre className="mt-2 overflow-auto text-xs text-slate-300">{JSON.stringify(image.fusion_plan, null, 2)}</pre>}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
