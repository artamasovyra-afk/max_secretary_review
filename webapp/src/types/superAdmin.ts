export type SuperAdminChatStatus = "pending_approval" | "active" | "rejected" | "suspended";

export interface SuperAdminSession {
  authenticated: boolean;
  login: string;
  session_expires_at: string | null;
}

export interface SuperAdminChat {
  id: string;
  display_title: string;
  display_title_source: "manual" | "real" | "fallback";
  status: SuperAdminChatStatus;
  type: string;
  deadline_reminders_enabled: boolean;
  members_count: number;
  chat_admins_count: number;
  max_admins_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface SuperAdminChatMember {
  id: string;
  user_id: string;
  display_name: string;
  username: string | null;
  role_in_dyak: "member" | "chat_admin" | "super_admin";
  is_active: boolean;
  is_max_chat_admin: boolean | null;
  has_max_user_id: boolean;
  updated_at: string;
}

export interface SuperAdminMaxAdminSyncResult {
  checked_members_count: number;
  max_admins_count: number;
  matched_admins_count: number;
  unknown_count: number;
  checked_at: string;
}

export interface SuperAdminMaxChatInfoSyncResult {
  title_updated: boolean;
  title_source: "max_api" | "manual" | "fallback";
  display_title: string;
}
