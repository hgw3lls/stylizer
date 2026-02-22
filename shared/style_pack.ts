export type StyleImageRef = {
  asset_id: string;
  path: string;
  mime_type: string;
};

export type Constraints = {
  palette?: string[];
  materials?: string[];
  line_rules: string[];
  composition_rules: string[];
  translation_rules: string[];
  forbidden: string[];
};

export type VariabilityKnobs = {
  drift: number;
  density: number;
  abstraction: number;
};

export type PromptAnchors = {
  base_prompt: string;
  negative_prompt: string;
  variability_knobs: VariabilityKnobs;
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
