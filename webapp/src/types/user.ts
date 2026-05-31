export interface User {
  id: string;
  max_user_id: string | null;
  display_name: string;
  username: string | null;
  phone: string | null;
  email: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserCreatePayload {
  max_user_id?: string | null;
  display_name: string;
  username?: string | null;
  phone?: string | null;
  email?: string | null;
}
