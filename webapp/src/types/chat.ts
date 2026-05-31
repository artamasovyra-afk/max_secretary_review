export interface Chat {
  id: string;
  organization_id: string;
  max_chat_id: string | null;
  title: string;
  type: string;
  status: "pending_approval" | "active" | "rejected" | "suspended";
  settings: Record<string, unknown> | null;
  display_title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatUpdatePayload {
  display_title?: string | null;
}

export interface ChatMember {
  id: string;
  chat_id: string;
  user_id: string;
  role: "member" | "chat_admin" | "super_admin";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
