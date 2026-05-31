import type { Chat } from "../types/chat";

interface ChatDisplayTitleInput {
  chat?: Pick<Chat, "display_title" | "settings" | "title" | "type"> | null;
  sourceTitle?: string | null;
}

const DISPLAY_TITLE_SETTING_KEYS = ["display_title", "title_alias", "display_name", "chat_title"];

export function getChatDisplayTitle({ chat, sourceTitle }: ChatDisplayTitleInput): string {
  const displayTitle = normalChatTitle(chat?.display_title);
  if (displayTitle) {
    return displayTitle;
  }

  const settingsTitle = settingsDisplayTitle(chat?.settings);
  if (settingsTitle) {
    return settingsTitle;
  }

  const storedTitle = normalChatTitle(chat?.title);
  if (storedTitle) {
    return storedTitle;
  }

  const snapshotTitle = normalChatTitle(sourceTitle);
  if (snapshotTitle) {
    return snapshotTitle;
  }

  return fallbackChatTitle(chat?.type);
}

export function isGeneratedMaxChatTitle(value: string | null | undefined): boolean {
  const normalized = value?.trim();
  return Boolean(normalized && /^max\s+(dialog|chat|group)\s+#/i.test(normalized));
}

function normalChatTitle(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  if (!normalized || isGeneratedMaxChatTitle(normalized)) {
    return null;
  }
  return normalized;
}

function settingsDisplayTitle(settings: Record<string, unknown> | null | undefined): string | null {
  if (!settings) {
    return null;
  }

  for (const key of DISPLAY_TITLE_SETTING_KEYS) {
    const value = settings[key];
    if (typeof value !== "string") {
      continue;
    }
    const title = normalChatTitle(value);
    if (title) {
      return title;
    }
  }

  return null;
}

function fallbackChatTitle(chatType: string | null | undefined): string {
  const normalized = chatType?.toLowerCase() ?? "";
  if (normalized.includes("dialog")) {
    return "Личный чат";
  }
  return "Чат без названия";
}
