import { z } from 'zod';
import type { HealthResponse, JobStatus, StylePack, TranslateResponse, TranslationJob } from './types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const stylePackIdSchema = z.string().uuid();
const translateOptionsSchema = z.object({
  size: z.string().default('1024x1024'),
  quality: z.string().default('high'),
  seed: z.number().int().optional(),
  variations: z.number().int().min(1).max(6),
  preserve_composition: z.boolean(),
  drift: z.number().min(0).max(1).optional(),
  density: z.number().min(0).max(1).optional(),
  abstraction: z.number().min(0).max(1).optional(),
  fusion_strategy: z.enum(['collage', 'poseA_bgB', 'motif_fusion']).optional(),
  dominance_weights: z.array(z.number()).optional(),
});

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorText = await response.text();
    throw new ApiError(errorText || `Request failed: ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return parseJson<HealthResponse>(await fetch(`${API_BASE}/health`));
}

export async function listStylePacks(): Promise<StylePack[]> {
  return parseJson<StylePack[]>(await fetch(`${API_BASE}/style-packs`));
}

export async function getStylePack(id: string): Promise<StylePack> {
  return parseJson<StylePack>(await fetch(`${API_BASE}/style-packs/${id}`));
}

export async function createStylePack(name: string, images: File[]): Promise<StylePack> {
  if (!name.trim()) throw new Error('Style pack name is required.');
  if (!images.length) throw new Error('Upload at least one image.');
  const form = new FormData();
  form.set('name', name);
  images.forEach((image) => form.append('images', image));
  return parseJson<StylePack>(await fetch(`${API_BASE}/style-packs`, { method: 'POST', body: form }));
}

export async function analyzeStylePack(id: string): Promise<StylePack> {
  return parseJson<StylePack>(await fetch(`${API_BASE}/style-packs/${id}/analyze`, { method: 'POST' }));
}

export async function createTranslateJob(payload: {
  stylePackId: string;
  mode: 'translate_single' | 'synthesize_multi';
  inputImages: File[];
  options: z.input<typeof translateOptionsSchema>;
}): Promise<{ job_id: string }> {
  stylePackIdSchema.parse(payload.stylePackId);
  const options = translateOptionsSchema.parse(payload.options);

  if (payload.mode === 'translate_single' && payload.inputImages.length < 1) {
    throw new Error('translate_single requires at least 1 image.');
  }
  if (payload.mode === 'synthesize_multi' && (payload.inputImages.length < 2 || payload.inputImages.length > 10)) {
    throw new Error('synthesize_multi requires 2 to 10 input images.');
  }

  const form = new FormData();
  form.set('style_pack_id', payload.stylePackId);
  form.set('mode', payload.mode);
  form.set('options', JSON.stringify(options));
  payload.inputImages.forEach((image) => form.append('input_images', image));

  return parseJson<{ job_id: string }>(await fetch(`${API_BASE}/jobs/translate`, { method: 'POST', body: form }));
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return parseJson<JobStatus>(await fetch(`${API_BASE}/jobs/${jobId}`));
}

export async function listJobs(): Promise<TranslationJob[]> {
  return parseJson<TranslationJob[]>(await fetch(`${API_BASE}/jobs`));
}

export function extractResult(status: JobStatus): TranslateResponse | null {
  if (status.status !== 'completed') return null;
  return status.result ?? null;
}
