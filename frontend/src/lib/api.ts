import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/types/api";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Single place where requests are authenticated.
 * 5.0-5.5: backend dev user header. 5.6: replaced by the Supabase session token.
 */
function authHeaders(): Record<string, string> {
  const devUser = process.env.NEXT_PUBLIC_DEV_USER_ID;
  return devUser ? { "X-Dev-User-Id": devUser } : {};
}

const auth: Middleware = {
  onRequest({ request }) {
    for (const [key, value] of Object.entries(authHeaders())) request.headers.set(key, value);
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: API_URL });
api.use(auth);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Turns an openapi-fetch result into data or a thrown ApiError (for TanStack Query). */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await call;
  } catch {
    // Network failure / backend down / CORS: surface a readable message, never "no data"
    throw new ApiError(0, "Backend non raggiungibile. È in esecuzione su " + API_URL + "?");
  }
  const { data, error, response } = result;
  if (error !== undefined || data === undefined) {
    throw new ApiError(response.status, errorMessage(error) ?? response.statusText);
  }
  return data;
}

/** FastAPI errors: `detail` is a string, or a list of validation errors (422). */
function errorMessage(error: unknown): string | null {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = d.loc?.filter((x) => x !== "body").join(" › ");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join(" · ");
  return null;
}
