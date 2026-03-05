/**
 * Cloudflare Worker — универсальный AI API прокси
 *
 * Проксирует запросы к любому AI API через URL-маршрутизацию:
 *   /claude/v1/messages  → api.anthropic.com/v1/messages
 *   /gemini/...          → generativelanguage.googleapis.com/...
 *   /groq/...            → api.groq.com/...
 *
 * Развертывание:
 * cd cloudflare && npx wrangler deploy
 */

const ROUTES = {
  claude: "https://api.anthropic.com",
  gemini: "https://generativelanguage.googleapis.com",
  groq: "https://api.groq.com",
};

export default {
  async fetch(request) {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
          "Access-Control-Allow-Headers": "*",
        },
      });
    }

    const url = new URL(request.url);
    const path = url.pathname; // e.g. /claude/v1/messages

    // Определяем провайдера по первому сегменту пути
    const match = path.match(/^\/(claude|gemini|groq)(\/.*)?$/);
    if (!match) {
      return new Response(
        JSON.stringify({
          error: "Unknown route. Use /claude/..., /gemini/..., or /groq/...",
          available: Object.keys(ROUTES),
        }),
        { status: 404, headers: { "Content-Type": "application/json" } }
      );
    }

    const provider = match[1];
    const remainingPath = match[2] || "";
    const targetUrl = ROUTES[provider] + remainingPath + url.search;

    // Пробрасываем все заголовки (x-api-key, Authorization, x-goog-api-key и т.д.)
    const headers = new Headers(request.headers);
    headers.delete("host");

    try {
      const response = await fetch(targetUrl, {
        method: request.method,
        headers: headers,
        body: request.method !== "GET" ? request.body : undefined,
      });

      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("Access-Control-Allow-Origin", "*");

      return new Response(response.body, {
        status: response.status,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: `Proxy error [${provider}]: ${err.message}` }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  },
};
