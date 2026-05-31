import { request } from "./client";
import type {
  SuperAdminChat,
  SuperAdminChatMember,
  SuperAdminChatStatus,
  SuperAdminMaxChatInfoSyncResult,
  SuperAdminMaxAdminSyncResult,
  SuperAdminSession,
} from "../types/superAdmin";

export function getSuperAdminSession(): Promise<SuperAdminSession> {
  return request<SuperAdminSession>("/super-admin/session");
}

export function loginSuperAdmin(payload: { login: string; password: string }): Promise<SuperAdminSession> {
  return request<SuperAdminSession>("/super-admin/login", {
    method: "POST",
    body: payload,
  });
}

export function logoutSuperAdmin(): Promise<{ status: string }> {
  return request<{ status: string }>("/super-admin/logout", {
    method: "POST",
  });
}

export function getSuperAdminChats(status?: SuperAdminChatStatus | "all"): Promise<SuperAdminChat[]> {
  return request<SuperAdminChat[]>("/super-admin/chats", {
    query: { status: status === "all" ? undefined : status },
  });
}

export function getSuperAdminChatMembers(chatId: string): Promise<SuperAdminChatMember[]> {
  return request<SuperAdminChatMember[]>(`/super-admin/chats/${chatId}/members`);
}

export function updateSuperAdminChatStatus(
  chatId: string,
  status: SuperAdminChatStatus,
): Promise<SuperAdminChat> {
  return request<SuperAdminChat>(`/super-admin/chats/${chatId}/status`, {
    method: "PATCH",
    body: { status },
  });
}

export function updateSuperAdminChatDisplayTitle(
  chatId: string,
  displayTitle: string | null,
): Promise<SuperAdminChat> {
  return request<SuperAdminChat>(`/super-admin/chats/${chatId}/display-title`, {
    method: "PATCH",
    body: { display_title: displayTitle },
  });
}

export function updateSuperAdminChatSettings(
  chatId: string,
  payload: { deadline_reminders_enabled: boolean },
): Promise<SuperAdminChat> {
  return request<SuperAdminChat>(`/super-admin/chats/${chatId}/settings`, {
    method: "PATCH",
    body: payload,
  });
}

export function updateSuperAdminChatMemberRole(
  chatId: string,
  userId: string,
  payload: { role: "member" | "chat_admin"; allow_remove_last_admin?: boolean },
): Promise<SuperAdminChatMember> {
  return request<SuperAdminChatMember>(`/super-admin/chats/${chatId}/members/${userId}/role`, {
    method: "PATCH",
    body: payload,
  });
}

export function syncSuperAdminChatMaxAdmins(chatId: string): Promise<SuperAdminMaxAdminSyncResult> {
  return request<SuperAdminMaxAdminSyncResult>(`/super-admin/chats/${chatId}/sync-max-admins`, {
    method: "POST",
  });
}

export function syncSuperAdminChatMaxInfo(chatId: string): Promise<SuperAdminMaxChatInfoSyncResult> {
  return request<SuperAdminMaxChatInfoSyncResult>(`/super-admin/chats/${chatId}/sync-max-chat-info`, {
    method: "POST",
  });
}
