export interface DevAuthState {
  userId: string | null;
  organizationId: string | null;
  chatId: string | null;
  roles: string[];
  isDevAuth: boolean;
  source: "query" | "none";
}

export function emptyDevAuthState(): DevAuthState {
  return {
    userId: null,
    organizationId: null,
    chatId: null,
    roles: [],
    isDevAuth: false,
    source: "none",
  };
}

export function parseDevAuthFromSearch(search: string): DevAuthState {
  const params = new URLSearchParams(search);
  const userId = cleanParam(params.get("user_id"));
  const organizationId = cleanParam(params.get("organization_id"));
  const chatId = cleanParam(params.get("chat_id"));
  const roles = parseRoles(params.get("roles"));

  return {
    userId,
    organizationId,
    chatId,
    roles,
    isDevAuth: Boolean(userId),
    source: userId ? "query" : "none",
  };
}

export function buildDevAuthSearch(state: DevAuthState): string {
  const params = new URLSearchParams();
  if (state.userId) {
    params.set("user_id", state.userId);
  }
  if (state.organizationId) {
    params.set("organization_id", state.organizationId);
  }
  if (state.chatId) {
    params.set("chat_id", state.chatId);
  }
  if (state.roles.length > 0) {
    params.set("roles", state.roles.join(","));
  }
  const value = params.toString();
  return value ? `?${value}` : "";
}

function cleanParam(value: string | null): string | null {
  const trimmed = value?.trim() ?? "";
  return trimmed || null;
}

function parseRoles(value: string | null): string[] {
  if (!value) {
    return [];
  }
  return value
    .split(",")
    .map((role) => role.trim())
    .filter(Boolean);
}
