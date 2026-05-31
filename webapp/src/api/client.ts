const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

export type QueryParamValue = boolean | number | string | null | undefined;
export type QueryParams = object;

export interface ApiAuthContext {
  userId: string | null;
  organizationId: string | null;
  chatId: string | null;
  roles: string[];
}

let currentAuthContext: ApiAuthContext | null = null;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: QueryParams;
}

export function buildQueryString(params: QueryParams = {}): string {
  const searchParams = new URLSearchParams();
  Object.entries(params as Record<string, QueryParamValue>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  return searchParams.toString();
}

export async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { body, credentials, headers, query, ...init } = options;
  const queryString = buildQueryString(query);
  const url = `${apiBaseUrl}${path}${queryString ? `?${queryString}` : ""}`;
  const authHeaders = buildAuthHeaders();
  const response = await fetch(url, {
    ...init,
    credentials: credentials ?? "include",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const contentType = response.headers.get("content-type") ?? "";
  const hasBody = response.status !== 204;
  const payload = hasBody
    ? contentType.includes("application/json")
      ? await response.json()
      : await response.text()
    : null;

  if (!response.ok) {
    throw new ApiError(getErrorMessage(response.status, payload), response.status, payload);
  }

  return payload as T;
}

export function setApiAuthContext(context: ApiAuthContext | null): void {
  currentAuthContext = context;
}

function getErrorMessage(status: number, payload: unknown): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return `API request failed: ${status}`;
}

function buildAuthHeaders(): Record<string, string> {
  if (!currentAuthContext?.userId) {
    return {};
  }

  const headers: Record<string, string> = {
    "X-User-Id": currentAuthContext.userId,
  };
  if (currentAuthContext.organizationId) {
    headers["X-Organization-Id"] = currentAuthContext.organizationId;
  }
  if (currentAuthContext.chatId) {
    headers["X-Chat-Id"] = currentAuthContext.chatId;
  }
  if (currentAuthContext.roles.length > 0) {
    headers["X-Roles"] = currentAuthContext.roles.join(",");
  }
  return headers;
}
