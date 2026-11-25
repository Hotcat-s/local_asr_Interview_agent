export type RecordingStatus =
  | "imported"
  | "transcribing"
  | "transcribed"
  | "analyzing"
  | "analyzed"
  | "failed";

export interface Recording {
  id: number;
  title: string;
  audio_path: string;
  status: RecordingStatus;
  duration: number;
  language: string;
  error_message: string;
  created_at: string;
  updated_at: string;
  transcribed_at: string;
  analyzed_at: string;
  qa_count: number;
  overall_score: number | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  speaker: string;
}

export interface Transcript {
  segments: TranscriptSegment[];
  duration: number;
  language: string;
  raw_text: string;
}

export interface QAPair {
  index: number;
  question: string;
  answer: string;
  question_speaker: string;
  answer_speaker: string;
  start: number;
  end: number;
}

export interface QAAnalysis {
  index: number;
  question: string;
  answer: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  reference_answer: string;
  suggestion: string;
}

export interface InterviewReport {
  overall_score: number;
  summary: string;
  items: QAAnalysis[];
  improvements: string[];
  created_at: string;
}

export interface RecordingDetail {
  recording: Recording;
  transcript: Transcript | null;
  qa_pairs: QAPair[];
  report: InterviewReport | null;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  recording_id: number;
  kind: "transcribe" | "analyze";
  status: JobStatus;
  stage: string;
  percent: number;
  message: string;
  detail: string;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface ModelInfo {
  key: string;
  name: string;
  path: string;
  exists: boolean;
}

export interface Health {
  status: string;
  version: string;
  data_dir: string;
  config_path: string;
  db_path: string;
  engine_loaded: boolean;
  models: ModelInfo[];
  models_ready: boolean;
  active_jobs: Job[];
}

export interface LLMConfig {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  temperature: number;
  max_tokens: number;
  timeout: number;
}

export interface AnalysisConfig {
  batch_size: number;
  max_chars_per_batch: number;
  concurrency: number;
  enable_summary: boolean;
}

export interface ModelConfig {
  asr: string;
  vad: string;
  punc: string;
  spk: string;
  device: string;
}

export interface Settings {
  models: ModelConfig;
  llm: LLMConfig;
  analysis: AnalysisConfig;
  data_dir: string;
  use_embedding_segmentation: boolean;
  embedding_model: string;
  db_path: string;
  config_path: string;
  chunk_seconds: number;
  theme: string;
  font_family: string;
  font_size: number;
}
