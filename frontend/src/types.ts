export type ComponentState = "ready" | "unavailable" | "unknown";

export interface HealthResponse {
  status: "alive" | "ready" | "degraded";
  version: string;
  ready: boolean;
  components?: {
    application: ComponentState;
    milvus: ComponentState;
    embedding: ComponentState;
    llm: ComponentState;
    registry: ComponentState;
  };
  error_type?: string | null;
}

export interface PublicConfig {
  embedding_provider: string;
  embedding_model: string;
  llm_provider: string;
  collection_name: string;
  allowed_extensions: string[];
  max_upload_size_mb: number;
  retrieval_top_k: number;
}

export interface DocumentRecord {
  document_key: string;
  display_name: string;
  status: string;
  chunk_count: number;
  file_type?: string | null;
  file_size_bytes?: number | null;
  active_index_id?: string | null;
  active_version_id?: string | null;
  version_count: number;
  error_type?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentRecord[];
  total: number;
}

export interface DocumentIndexRecord {
  index_id: string;
  document_version_id: string;
  version_number: number;
  status: string;
  chunk_count: number;
  error_type?: string | null;
  file_type: string;
  file_size_bytes: number;
  source_sha256: string;
  created_at: string;
  updated_at: string;
  activated_at?: string | null;
  is_active: boolean;
}

export interface DocumentDetail extends DocumentRecord {
  indexes: DocumentIndexRecord[];
}

export interface IngestionResponse {
  status: string;
  operation_id: string;
  document_key: string;
  document_version_id: string;
  source_sha256: string;
  index_id: string;
  chunk_count: number;
  collection_count: number;
  previous_index_id?: string | null;
  cleanup_pending: boolean;
}

export interface DocumentDeletionResponse {
  status: string;
  document_key: string;
  deleted_index_count: number;
  deleted_chunk_count: number;
  collection_count: number;
  cleanup_pending: boolean;
}

export interface SourceReference {
  rank: number;
  source: string;
  page_number?: number | null;
  excerpt: string;
  distance?: number | null;
  lexical_score?: number | null;
  fusion_score?: number | null;
  rerank_score?: number | null;
  chunk_id?: string | null;
}

export interface ErrorResponse {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}

export type ChatStage = "idle" | "retrieving" | "generating" | "done" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  stage: ChatStage;
  sources: SourceReference[];
}

export type ChatEvent =
  | { type: "status"; data: { stage: "retrieving" | "generating" } }
  | { type: "sources"; data: { items: SourceReference[] } }
  | { type: "token"; data: { text: string } }
  | {
      type: "done";
      data: { status: "success" | "no_context"; message?: string };
    }
  | {
      type: "error";
      data: { code: string; message: string; partial: boolean; retryable: boolean };
    };
