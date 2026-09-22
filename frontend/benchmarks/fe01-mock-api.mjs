import { createHash } from "node:crypto";
import http from "node:http";

const host = "127.0.0.1";
const port = 4274;
const targetLength = 10_000;
const chunkSize = 50;
const chunkIntervalMs = 10;
const finalMarker = "\n\nBENCHMARK_END";

const section = `
## 固定基线段落

DocuMind 使用检索结果生成回答，并保留来源映射以便核对。[文档1]

- 第一项说明流式正文需要完整保留。
- 第二项说明历史消息不应重复解析。
- 第三项说明阅读上文时不应被自动滚动打断。[文档2]

| 指标 | 目标 | 说明 |
| --- | ---: | --- |
| 刷新间隔 | 50ms | 合并高频 token |
| 可见延迟 | 100ms | 前台隔离 Mock |

\`\`\`typescript
function appendChunk(current: string, chunk: string): string {
  return current + chunk;
}
\`\`\`

这段中文内容固定重复，用于让 Markdown、表格、列表、代码和引用同时进入渲染路径。
`;

function createAnswer() {
  let answer = "# 高频流式基线\n";
  while (answer.length + section.length + finalMarker.length <= targetLength) {
    answer += section;
  }
  const filler = "补充说明保持固定输入并继续引用来源[文档1]。";
  while (answer.length + filler.length + finalMarker.length <= targetLength) {
    answer += filler;
  }
  const remaining = targetLength - finalMarker.length - answer.length;
  answer += filler.slice(0, remaining);
  return answer + finalMarker;
}

const answer = createAnswer();
const chunks = [];
for (let offset = 0; offset < answer.length; offset += chunkSize) {
  chunks.push(answer.slice(offset, offset + chunkSize));
}

const fixture = {
  answerLength: answer.length,
  answerSha256: createHash("sha256").update(answer, "utf8").digest("hex"),
  chunkCount: chunks.length,
  chunkSize,
  chunkIntervalMs,
  historyMessageCount: 50,
};

let lastRun = null;

function corsHeaders(contentType = "application/json; charset=utf-8") {
  return {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Origin": "*",
    "Content-Type": contentType,
  };
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, corsHeaders());
  response.end(JSON.stringify(payload));
}

function writeEvent(response, event, data) {
  response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

function streamBenchmark(response) {
  response.writeHead(200, {
    ...corsHeaders("text/event-stream; charset=utf-8"),
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });
  writeEvent(response, "status", { stage: "retrieving" });
  writeEvent(response, "sources", {
    items: [
      {
        rank: 1,
        source: "baseline-guide.txt",
        page_number: 1,
        excerpt: "固定基线来源一。",
        distance: 0.1,
        chunk_id: "baseline-chunk-1",
      },
      {
        rank: 2,
        source: "baseline-reference.txt",
        page_number: 2,
        excerpt: "固定基线来源二。",
        distance: 0.2,
        chunk_id: "baseline-chunk-2",
      },
    ],
  });
  writeEvent(response, "status", { stage: "generating" });

  const startedAt = performance.now();
  const sentAt = [];
  let index = 0;
  let finished = false;
  const timer = setInterval(() => {
    if (index < chunks.length) {
      writeEvent(response, "token", { text: chunks[index] });
      sentAt.push(performance.now() - startedAt);
      index += 1;
      return;
    }
    clearInterval(timer);
    writeEvent(response, "done", { status: "success" });
    finished = true;
    lastRun = {
      sentChunkCount: index,
      durationMs: performance.now() - startedAt,
      sentAt,
    };
    response.end();
  }, chunkIntervalMs);

  response.on("close", () => {
    if (!finished) clearInterval(timer);
  });
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host}`);
  if (request.method === "OPTIONS") {
    response.writeHead(204, corsHeaders());
    response.end();
    return;
  }
  if (url.pathname === "/__fe01/health") {
    sendJson(response, 200, { status: "ok" });
    return;
  }
  if (url.pathname === "/__fe01/fixture") {
    sendJson(response, 200, fixture);
    return;
  }
  if (url.pathname === "/__fe01/last-run") {
    sendJson(response, 200, { lastRun });
    return;
  }
  if (url.pathname === "/api/v1/health/ready") {
    sendJson(response, 200, {
      status: "ready",
      version: "3.1.0",
      ready: true,
      components: {
        application: "ready",
        milvus: "ready",
        embedding: "ready",
        llm: "ready",
        registry: "ready",
        retrieval: "ready",
      },
      error_type: null,
    });
    return;
  }
  if (url.pathname === "/api/v1/system/config") {
    sendJson(response, 200, {
      embedding_provider: "fixture",
      embedding_model: "fixed-stream-v1",
      llm_provider: "fixture",
      collection_name: "fe01_baseline",
      allowed_extensions: [".txt"],
      max_upload_size_mb: 1,
      retrieval_top_k: 2,
    });
    return;
  }
  if (url.pathname === "/api/v1/documents") {
    sendJson(response, 200, { items: [], total: 0 });
    return;
  }
  if (url.pathname === "/api/v1/chat/stream" && request.method === "POST") {
    await readBody(request);
    streamBenchmark(response);
    return;
  }
  sendJson(response, 404, {
    error: { code: "not_found", message: "Not found" },
  });
});

server.listen(port, host, () => {
  console.log(`FE-01 benchmark API listening on http://${host}:${port}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
