export type AuthSource = "dev" | "existing_session" | "max_webapp" | "none";

export interface AuthUser {
  id: string;
  display_name: string;
  username: string | null;
  roles: string[];
}

export interface AuthChatContext {
  id: string;
  organization_id: string;
  title: string;
  role: string;
}

export interface AuthSession {
  user: AuthUser;
  context: {
    organization_id: string | null;
    chat_id: string | null;
    available_chats: AuthChatContext[];
  };
  session_expires_at: string | null;
}
