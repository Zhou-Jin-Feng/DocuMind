import http from "node:http";

const host = "127.0.0.1";
const port = Number(process.env.E2E_API_PORT || 4174);

function initialState() {
  return {
    online: true,
    streamMode: "complete",
    documents: [],
    uploadCount: 0,
    streamRequests: 0,
    abortedStreams: 0,
  };
}

let state = initialState();

function corsHeaders(contentType = "application/json; charset=utf-8") {
  return {
    "Access-Control-Allow-Headers": "Content-Type, X-Request-ID",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Origin": "*",
    "Content-Type": contentType,
  };
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, corsHeaders());
  response.end(JSON.stringify(payload));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

function writeEvent(response, event, data) {
  response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function readyComponents() {
  return {
    application: "ready",
    milvus: "ready",
    embedding: "ready",
    llm: "ready",
    registry: "ready",
  };
}

async function handleControl(request, response, url) {
  if (url.pathname === "/__e2e/health") {
    sendJson(response, 200, { status: "ok" });
    return true;
  }
  if (url.pathname === "/__e2e/reset" && request.method === "POST") {
    state = initialState();
    sendJson(response, 200, state);
    return true;
  }
  if (url.pathname === "/__e2e/state" && request.method === "GET") {
    sendJson(response, 200, state);
    return true;
  }
  if (url.pathname === "/__e2e/state" && request.method === "POST") {
    const body = JSON.parse((await readBody(request)).toString("utf-8") || "{}");
    state = { ...state, ...body };
    sendJson(response, 200, state);
    return true;
  }
  return false;
}

function streamChat(request, response) {
  state.streamRequests += 1;
  response.writeHead(200, {
    ...corsHeaders("text/event-stream; charset=utf-8"),
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });

  let finished = false;
  let interval;
  response.on("close", () => {
    if (!finished) {
      state.abortedStreams += 1;
    }
    if (interval) {
      clearInterval(interval);
    }
  });

  writeEvent(response, "status", { stage: "retrieving" });
  writeEvent(response, "sources", {
    items: [
      {
        rank: 1,
        source: "guide.txt",
        page_number: 1,
        excerpt: "RAG 通过检索外部知识增强模型回答。",
        distance: 0.125,
        chunk_id: "chunk-1",
      },
    ],
  });
  writeEvent(response, "status", { stage: "generating" });

  if (state.streamMode === "slow") {
    writeEvent(response, "token", { text: "部分回答" });
    interval = setInterval(() => {
      writeEvent(response, "token", { text: "。" });
    }, 250);
    return;
  }

  writeEvent(response, "token", { text: "RAG 是检索增强生成技术。" });
  writeEvent(response, "done", { status: "success" });
  finished = true;
  response.end();
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host}`);
  if (request.method === "OPTIONS") {
    response.writeHead(204, corsHeaders());
    response.end();
    return;
  }
  if (await handleControl(request, response, url)) {
    return;
  }
  if (!state.online) {
    sendJson(response, 503, {
      error: { code: "service_unavailable", message: "测试后端暂不可用" },
    });
    return;
  }

  if (url.pathname === "/api/v1/health/ready" && request.method === "GET") {
    sendJson(response, 200, {
      status: "ready",
      version: "1.9.1",
      ready: true,
      components: readyComponents(),
      error_type: null,
    });
    return;
  }
  if (url.pathname === "/api/v1/system/config" && request.method === "GET") {
    sendJson(response, 200, {
      embedding_provider: "ollama",
      embedding_model: "qwen3-embedding",
      llm_provider: "deepseek",
      collection_name: "rag_documents",
      allowed_extensions: [".pdf", ".docx", ".txt"],
      max_upload_size_mb: 50,
      retrieval_top_k: 3,
    });
    return;
  }
  if (url.pathname === "/api/v1/documents" && request.method === "GET") {
    sendJson(response, 200, {
      items: state.documents,
      total: state.documents.length,
    });
    return;
  }
  if (url.pathname === "/api/v1/documents" && request.method === "POST") {
    const body = (await readBody(request)).toString("utf-8");
    const filename = /filename="([^"]+)"/.exec(body)?.[1] || "guide.txt";
    const timestamp = new Date().toISOString();
    state.uploadCount += 1;
    state.documents = [
      {
        document_key: "doc-guide",
        display_name: filename,
        status: "active",
        chunk_count: 3,
        file_type: ".txt",
        file_size_bytes: 42,
        active_index_id: "index-guide",
        created_at: timestamp,
        updated_at: timestamp,
      },
    ];
    sendJson(response, 200, {
      status: "indexed",
      operation_id: "operation-guide",
      document_key: "doc-guide",
      document_version_id: "version-guide",
      source_sha256: "sha256-guide",
      index_id: "index-guide",
      chunk_count: 3,
      collection_count: 3,
      cleanup_pending: false,
    });
    return;
  }
  if (url.pathname === "/api/v1/chat/stream" && request.method === "POST") {
    await readBody(request);
    streamChat(request, response);
    return;
  }

  sendJson(response, 404, {
    error: { code: "not_found", message: "Not found" },
  });
});

server.listen(port, host, () => {
  console.log(`E2E mock API listening on http://${host}:${port}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
