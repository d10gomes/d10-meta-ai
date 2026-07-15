import axios from "axios";

// NEXT_PUBLIC_API_URL can arrive with a BOM prefix (U+FEFF) when set via Vercel CLI.
// Validate that it starts with "http"; fall back to localhost otherwise.
function getSafeApiUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "";
  const cleaned = raw.replace(/[^\x20-\x7E]/g, "").trim();
  return cleaned.startsWith("http") ? cleaned : "http://localhost:8000";
}

const API_URL = getSafeApiUrl();

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  // Add trailing slash on GET requests to avoid FastAPI 307 redirect stripping Authorization header
  if (config.method === "get" && config.url) {
    const [path, qs] = config.url.split("?");
    if (!path.endsWith("/")) {
      config.url = path + "/" + (qs ? "?" + qs : "");
    }
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);