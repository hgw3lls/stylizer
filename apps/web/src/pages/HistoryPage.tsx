import { useQuery } from '@tanstack/react-query';
import { listJobs } from '../lib';

export function HistoryPage() {
  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: 5000 });

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-4">
      <h2 className="text-xl font-semibold">History</h2>
      {jobsQuery.isLoading && <p className="mt-2 text-sm text-slate-400">Loading jobs...</p>}
      {jobsQuery.error && <p className="mt-2 text-sm text-rose-400">{jobsQuery.error.message}</p>}
      <div className="mt-3 space-y-3">
        {jobsQuery.data?.map((job) => (
          <article key={job.id} className="rounded border border-slate-700 bg-slate-950 p-3">
            <p className="text-sm font-medium">{job.mode}</p>
            <p className="text-xs text-slate-400">Pack: {job.style_pack_id}</p>
            <p className="text-xs text-slate-400">{new Date(job.created_at).toLocaleString()}</p>
            <div className="mt-2 grid gap-2 md:grid-cols-4">
              {job.outputs.map((output, idx) => (
                <img key={idx} src={`data:image/png;base64,${output.image_base64}`} className="rounded" />
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
