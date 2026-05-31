import { request } from "./client";
import type { AuthSession } from "../types/auth";

export function createMaxWebAppSession(initData: string): Promise<AuthSession> {
  return request<AuthSession>("/auth/max-webapp/session", {
    method: "POST",
    body: {
      init_data: initData,
    },
  });
}

export function getCurrentAuthSession(): Promise<AuthSession> {
  return request<AuthSession>("/auth/me");
}

export function logoutAuthSession(): Promise<{ status: string }> {
  return request<{ status: string }>("/auth/logout", {
    method: "POST",
  });
}
