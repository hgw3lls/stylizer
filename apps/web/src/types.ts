export type HealthResponse = { status: 'ok'; service: string };

export type StyleImageRef = { asset_id: string; path: string; mime_type: string };

export type Constraints = {
  palette?: string[];
  materials?: string[];
  line_rules: string[];
  composition_rules: string[];
  translation_rules: string[];
  forbidden: string[];
};

export type PromptAnchors = {
  base_prompt: string;
  negative_prompt: string;
  variability_knobs: { drift: number; density: number; abstraction: number };
};

export type StylePack = {
  id: string;
  name: string;
  created_at: string;
  style_images: StyleImageRef[];
  constraints: Constraints;
  prompt_anchors: PromptAnchors;
  version: string;
};

export type FusionPlan = {
  subject_from: number;
  background_from: number;
  motifs_from: number[];
  composition_notes: string;
  exclusions: string[];
  dominance_weights: number[];
};

export type TranslateOutput = { image_base64: string; fusion_plan?: FusionPlan | null };

export type TranslateResponse = {
  style_pack_id: string;
  mode: 'translate_single' | 'synthesize_multi';
  prompt_used: string;
  created_at: string;
  images: TranslateOutput[];
};

export type TranslationJob = {
  id: string;
  style_pack_id: string;
  mode: string;
  prompt_used: string;
  created_at: string;
  outputs: TranslateOutput[];
};


export type JobStatus = {
  job_id: string;
  status: string;
  error_message?: string | null;
  result?: TranslateResponse | null;
};
