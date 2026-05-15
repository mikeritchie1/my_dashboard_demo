function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(),
    },
  });
}

function getStateKey(url) {
  const raw = String(url.searchParams.get("key") || "").trim();
  return raw || "main";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (url.pathname !== "/state") {
      return jsonResponse({ error: "Not found" }, 404);
    }

    const key = getStateKey(url);

    if (request.method === "GET") {
      const raw = await env.DASH_STATE.get(key);
      if (!raw) {
        return jsonResponse({});
      }
      try {
        return jsonResponse(JSON.parse(raw));
      } catch {
        return jsonResponse({});
      }
    }

    if (request.method === "POST") {
      let body = null;
      try {
        body = await request.json();
      } catch {
        return jsonResponse({ error: "Invalid JSON" }, 400);
      }
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        return jsonResponse({ error: "Payload must be an object" }, 400);
      }
      await env.DASH_STATE.put(key, JSON.stringify(body));
      return jsonResponse({ ok: true });
    }

    return jsonResponse({ error: "Method not allowed" }, 405);
  },
};
