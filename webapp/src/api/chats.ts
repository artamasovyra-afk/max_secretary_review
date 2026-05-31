import { request } from "./client";
import type { Chat, ChatMember, ChatUpdatePayload } from "../types/chat";

export function getChats(): Promise<Chat[]> {
  return request<Chat[]>("/chats");
}

export function getChat(chatId: string): Promise<Chat> {
  return request<Chat>(`/chats/${chatId}`);
}

export function getChatMembers(chatId: string): Promise<ChatMember[]> {
  return request<ChatMember[]>(`/chats/${chatId}/members`);
}

export function updateChat(chatId: string, payload: ChatUpdatePayload): Promise<Chat> {
  return request<Chat>(`/chats/${chatId}`, {
    method: "PATCH",
    body: payload,
  });
}

export const listChats = getChats;
export const listChatMembers = getChatMembers;
