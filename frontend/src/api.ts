import type {
  ChatEvent,
  DocumentListResponse,
  ErrorResponse,
  HealthResponse,
  IngestionResponse,
  PublicConfig,
} from "./types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001"
).replace(/\/$/, "");

export class APIError extends Error {
  code: string;
  requestId?: string;

  constructor(message: string, code = "request_failed", requestId?: string) {
    super(message);
    this.name = "APIError";
    this.code = code;
    this.requestId = requestId;
  }
}

async function parseError(response: Response): Promise<APIError> {
  let payload: ErrorResponse | undefined;
  try {
    payload = (await response.json()) as ErrorResponse;
  } catch {
    payload = undefined;
  }
  return new APIError(
    payload?.error?.message || `请求失败 (${response.status})`,
    payload?.error?.code,
    payload?.error?.request_id || response.headers.get("X-Request-ID") || undefined,
  );
}

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export async function getReadiness(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health/ready`, {
    headers: { Accept: "application/json" },
  });
  const payload = (await response.json()) as HealthResponse | ErrorResponse;
  if ("status" in payload) {
    return payload;
  }
  throw new APIError(
    payload.error?.message || "无法读取服务状态",
    payload.error?.code,
    payload.error?.request_id,
  );
}

export function getPublicConfig(): Promise<PublicConfig> {
  return getJSON<PublicConfig>("/api/v1/system/config");
}

export function getDocuments(): Promise<DocumentListResponse> {
  return getJSON<DocumentListResponse>("/api/v1/documents");
}

export async function uploadDocument(file: File): Promise<IngestionResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as IngestionResponse;
}

interface StreamCallbacks {
  onEvent: (event: ChatEvent) => void;
}

function parseSSEBlock(block: string): ChatEvent | null {
  let eventType = "";
  const dataLines: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!eventType || dataLines.length === 0) {
    return null;
  }
  return {
    type: eventType,
    data: JSON.parse(dataLines.join("\n")) as unknown,
  } as ChatEvent;
}

export async function streamChat(
  question: string,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  if (!response.body) {
    throw new APIError("浏览器未收到流式响应", "empty_stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = parseSSEBlock(block);
      if (event) {
        callbacks.onEvent(event);
      }
    }
    if (done) {
      const event = parseSSEBlock(buffer);
      if (event) {
        callbacks.onEvent(event);
      }
      return;
    }
  }
}
