import http from "node:http";

const host = "127.0.0.1";
const port = Number(process.env.E2E_API_PORT || 4174);

function initialState() {
  return {
    online: true,
    streamMode: "complete",
    documents: [],
    uploadCount: 0,
    uploadDelayMs: 0,
    holdDeleteResponse: false,
    deletePending: false,
    deleteRequestCount: 0,
    reindexCount: 0,
    deleteCount: 0,
    streamRequests: 0,
    abortedStreams: 0,
    streamQuestions: [],
    raceBPending: false,
  };
}

let state = initialState();
let pendingRaceB = null;
let pendingDelete = null;

function corsHeaders(contentType = "application/json; charset=utf-8") {
  return {
    "Access-Control-Allow-Headers": "Content-Type, X-Request-ID",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
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

function documentDetail(document) {
  return {
    ...document,
    indexes: [
      {
        index_id: document.active_index_id,
        document_version_id: document.active_version_id,
        version_number: 1,
        status: "active",
        chunk_count: document.chunk_count,
        error_type: null,
        file_type: document.file_type,
        file_size_bytes: document.file_size_bytes,
        source_sha256: "sha256-guide",
        created_at: document.created_at,
        updated_at: document.updated_at,
        activated_at: document.updated_at,
        is_active: true,
      },
    ],
  };
}

async function handleControl(request, response, url) {
  if (url.pathname === "/__e2e/health") {
    sendJson(response, 200, { status: "ok" });
    return true;
  }
  if (url.pathname === "/__e2e/reset" && request.method === "POST") {
    pendingRaceB?.cancel();
    pendingRaceB = null;
    pendingDelete?.release(false);
    pendingDelete = null;
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
  if (url.pathname === "/__e2e/release-race-b" && request.method === "POST") {
    if (!pendingRaceB?.release()) {
      sendJson(response, 409, {
        error: { code: "race_b_not_pending", message: "Race stream B is not pending." },
      });
      return true;
    }
    sendJson(response, 200, state);
    return true;
  }
  if (url.pathname === "/__e2e/release-delete" && request.method === "POST") {
    if (!pendingDelete?.release(true)) {
      sendJson(response, 409, {
        error: { code: "delete_not_pending", message: "Delete is not pending." },
      });
      return true;
    }
    sendJson(response, 200, state);
    return true;
  }
  return false;
}

function streamChat(request, response, question) {
  state.streamRequests += 1;
  const requestNumber = state.streamRequests;
  const streamMode = state.streamMode;
  state.streamQuestions.push(question);
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
    if (pendingRaceB?.response === response) {
      pendingRaceB = null;
      state.raceBPending = false;
    }
    if (interval) {
      clearInterval(interval);
    }
  });

  writeEvent(response, "status", { stage: "retrieving" });
  if (streamMode === "final-review-matrix") {
    let lastStep = -1;
    interval = setInterval(() => {
      const step = state.reviewStep ?? 0;
      if (step === lastStep) return;
      lastStep = step;
      if (step === 0) {
        writeEvent(response, "status", { stage: "generating" });
        writeEvent(response, "token", { text: "流式引用 [文档" });
      } else if (step === 1) {
        writeEvent(response, "token", { text: "1]。" });
      } else if (step === 2) {
        writeEvent(response, "sources", {
          items: [{ rank: 1, source: "late.txt", excerpt: "晚到来源", chunk_id: "late-1" }],
        });
      } else if (step === 3) {
        writeEvent(response, "token", { text: "\n\n```python\ndef answer():\n    return 42" });
      } else if (step === 4) {
        writeEvent(response, "token", { text: "\n```" });
        writeEvent(response, "done", { status: "success" });
        finished = true;
        clearInterval(interval);
        response.end();
      }
    }, 20);
    return;
  }
  const raceRequest = streamMode === "conversation-race";
  const source = raceRequest
    ? requestNumber === 1
      ? {
          rank: 1,
          source: "source-a.txt",
          page_number: 1,
          excerpt: "A 请求的来源，不能污染 B。",
          distance: 0.111,
          chunk_id: "chunk-a",
        }
      : {
          rank: 1,
          source: "source-b.txt",
          page_number: 2,
          excerpt: "B 请求的来源，必须保持为当前来源。",
          distance: 0.222,
          chunk_id: "chunk-b",
        }
    : {
        rank: 1,
        source: "guide.txt",
        page_number: 1,
        excerpt: "RAG 通过检索外部知识增强模型回答。",
        distance: 0.125,
        chunk_id: "chunk-1",
      };
  writeEvent(response, "sources", {
    items: [source],
  });
  writeEvent(response, "status", { stage: "generating" });

  if (raceRequest && requestNumber === 1) {
    writeEvent(response, "token", { text: "A 部分回答" });
    return;
  }

  if (raceRequest && requestNumber === 2) {
    state.raceBPending = true;
    pendingRaceB = {
      response,
      release() {
        if (finished || response.destroyed || response.writableEnded) return false;
        writeEvent(response, "token", { text: "B 完整回答" });
        writeEvent(response, "done", { status: "success" });
        finished = true;
        state.raceBPending = false;
        pendingRaceB = null;
        response.end();
        return true;
      },
      cancel() {
        if (finished) return;
        finished = true;
        state.raceBPending = false;
        if (!response.writableEnded) response.end();
      },
    };
    return;
  }

  if (streamMode === "slow") {
    writeEvent(response, "token", { text: "部分回答" });
    interval = setInterval(() => {
      writeEvent(response, "token", { text: "。" });
    }, 250);
    return;
  }

  writeEvent(response, "token", {
    text:
      streamMode === "g2-citation"
        ? "Fresh answer [文档1]."
        : "RAG 是检索增强生成技术。",
  });
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
      version: "3.1.0",
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
        active_version_id: "version-guide",
        version_count: 1,
        error_type: null,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ];
    if (state.uploadDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, state.uploadDelayMs));
    }
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
  const reindexMatch = url.pathname.match(
    /^\/api\/v1\/documents\/([^/]+)\/reindex$/,
  );
  if (reindexMatch && request.method === "POST") {
    const documentKey = decodeURIComponent(reindexMatch[1]);
    const document = state.documents.find(
      (item) => item.document_key === documentKey,
    );
    if (!document) {
      sendJson(response, 404, {
        error: { code: "document_not_found", message: "未找到该文档。" },
      });
      return;
    }
    const updatedAt = new Date().toISOString();
    state.reindexCount += 1;
    state.documents = state.documents.map((item) =>
      item.document_key === documentKey
        ? { ...item, updated_at: updatedAt }
        : item,
    );
    sendJson(response, 200, {
      status: "indexed",
      operation_id: "operation-reindex-guide",
      document_key: documentKey,
      document_version_id: "version-guide",
      source_sha256: "sha256-guide",
      index_id: "index-guide",
      chunk_count: 3,
      collection_count: 3,
      cleanup_pending: false,
    });
    return;
  }
  const documentMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)$/);
  if (documentMatch && request.method === "GET") {
    const documentKey = decodeURIComponent(documentMatch[1]);
    const document = state.documents.find(
      (item) => item.document_key === documentKey,
    );
    if (!document) {
      sendJson(response, 404, {
        error: { code: "document_not_found", message: "未找到该文档。" },
      });
      return;
    }
    sendJson(response, 200, documentDetail(document));
    return;
  }
  if (documentMatch && request.method === "DELETE") {
    const documentKey = decodeURIComponent(documentMatch[1]);
    const exists = state.documents.some(
      (item) => item.document_key === documentKey,
    );
    if (!exists) {
      sendJson(response, 404, {
        error: { code: "document_not_found", message: "未找到该文档。" },
      });
      return;
    }
    state.deleteRequestCount += 1;
    if (state.holdDeleteResponse) {
      state.deletePending = true;
      const proceed = await new Promise((resolve) => {
        const gate = {
          release(value) {
            if (pendingDelete !== gate) return false;
            pendingDelete = null;
            state.deletePending = false;
            resolve(value);
            return true;
          },
        };
        pendingDelete = gate;
      });
      if (!proceed) {
        sendJson(response, 409, {
          error: { code: "delete_cancelled", message: "Delete gate was reset." },
        });
        return;
      }
    }
    state.deleteCount += 1;
    state.documents = state.documents.filter(
      (item) => item.document_key !== documentKey,
    );
    sendJson(response, 200, {
      status: "deleted",
      document_key: documentKey,
      deleted_index_count: 1,
      deleted_chunk_count: 3,
      collection_count: 0,
      cleanup_pending: false,
    });
    return;
  }
  if (url.pathname === "/api/v1/chat/stream" && request.method === "POST") {
    const body = (await readBody(request)).toString("utf-8");
    let question = "";
    try {
      const payload = JSON.parse(body || "{}");
      question = typeof payload.question === "string" ? payload.question : "";
    } catch {
      question = "";
    }
    streamChat(request, response, question);
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
