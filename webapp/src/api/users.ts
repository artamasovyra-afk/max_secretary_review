import { request } from "./client";
import type { User, UserCreatePayload } from "../types/user";

export function getUsers(): Promise<User[]> {
  return request<User[]>("/users");
}

export function getUser(userId: string): Promise<User> {
  return request<User>(`/users/${userId}`);
}

export function createUser(payload: UserCreatePayload): Promise<User> {
  return request<User>("/users", {
    method: "POST",
    body: payload,
  });
}

export const listUsers = getUsers;
