const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function api<T>(path: string, options: RequestInit, token: string): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers } });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.error?.message ?? `API error ${response.status}`);
  return body as T;
}
