export const PROJECT_TIME_ZONE = "Asia/Yekaterinburg";

export function formatProjectDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    timeZone: PROJECT_TIME_ZONE,
    year: "numeric",
  }).format(new Date(value));
}
