import { BellOutlined, RobotOutlined, SafetyOutlined, TeamOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Input, List, Space, Tag, Typography, notification } from "antd";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { getChats, updateChat } from "../api/chats";
import { useAuth } from "../auth/useAuth";
import type { Chat } from "../types/chat";
import { getChatDisplayTitle } from "../utils/chatDisplayTitle";

const plannedSections = [
  {
    title: "Профиль пользователя",
    description: "Личные параметры и будущая MAX WebApp авторизация.",
    icon: <UserOutlined />,
  },
  {
    title: "Уведомления и напоминания",
    description: "Настройки сроков, повторов и персональных напоминаний.",
    icon: <BellOutlined />,
  },
  {
    title: "Интеграции MAX",
    description: "Webhook, отправка сообщений и chat-native действия.",
    icon: <RobotOutlined />,
  },
  {
    title: "Интеграции Битрикс24",
    description: "Ручная синхронизация, mapping пользователей и статусы.",
    icon: <SafetyOutlined />,
  },
  {
    title: "Пользователи и роли",
    description: "Участники, права доступа и администрирование чатов.",
    icon: <TeamOutlined />,
  },
];

export function SettingsPage() {
  const auth = useAuth();
  const [notificationApi, notificationContextHolder] = notification.useNotification();
  const [chats, setChats] = useState<Chat[]>([]);
  const [chatAliasValues, setChatAliasValues] = useState<Record<string, string>>({});
  const [chatAliasSaving, setChatAliasSaving] = useState<Record<string, boolean>>({});
  const [chatAliasError, setChatAliasError] = useState<string | null>(null);
  const displayName = auth.user?.display_name ?? "Не определен";
  const isSuperAdmin = auth.roles.includes("super_admin");
  const editableChatIds = useMemo(
    () => {
      const ids = new Set(
        auth.availableChats
          .filter((chat) => chat.role === "chat_admin" || chat.role === "super_admin")
          .map((chat) => chat.id),
      );
      if (auth.chatId && auth.roles.includes("chat_admin")) {
        ids.add(auth.chatId);
      }
      return ids;
    },
    [auth.availableChats, auth.chatId, auth.roles],
  );
  const editableChats = useMemo(
    () => chats.filter((chat) => isSuperAdmin || editableChatIds.has(chat.id)),
    [chats, editableChatIds, isSuperAdmin],
  );
  const roles =
    auth.roles.length > 0 ? (
      <span className="settings-session-tags">
        {auth.roles.map((role) => (
          <Tag key={role}>{role}</Tag>
        ))}
      </span>
    ) : (
      <Tag>Нет</Tag>
    );

  useEffect(() => {
    if (!auth.authenticated) {
      return;
    }
    getChats()
      .then((nextChats) => {
        setChats(nextChats);
        setChatAliasError(null);
        setChatAliasValues((current) => {
          const nextValues = { ...current };
          for (const chat of nextChats) {
            if (!(chat.id in nextValues)) {
              nextValues[chat.id] = chat.display_title ?? settingsDisplayTitle(chat.settings) ?? "";
            }
          }
          return nextValues;
        });
      })
      .catch((error: unknown) => {
        setChats([]);
        setChatAliasError(error instanceof Error ? error.message : "Не удалось загрузить список чатов.");
      });
  }, [auth.authenticated]);

  const saveChatAlias = async (chat: Chat) => {
    const displayTitle = (chatAliasValues[chat.id] ?? "").trim();
    setChatAliasSaving((current) => ({ ...current, [chat.id]: true }));
    try {
      const updated = await updateChat(chat.id, { display_title: displayTitle || null });
      setChats((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setChatAliasValues((current) => ({
        ...current,
        [chat.id]: updated.display_title ?? settingsDisplayTitle(updated.settings) ?? "",
      }));
      notificationApi.success({
        message: "Название чата сохранено",
        description: getChatDisplayTitle({ chat: updated }),
      });
    } catch (error: unknown) {
      notificationApi.error({
        message: "Не удалось сохранить название чата",
        description: error instanceof Error ? error.message : "Проверьте права и попробуйте еще раз.",
      });
    } finally {
      setChatAliasSaving((current) => ({ ...current, [chat.id]: false }));
    }
  };

  return (
    <main className="page">
      {notificationContextHolder}
      <div className="page-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={2}>Настройки</Typography.Title>
          <Typography.Text type="secondary">Раздел готовится к пилотному использованию</Typography.Text>
        </Space>
      </div>

      <Card className="settings-card" title="Текущая сессия">
        <Space direction="vertical" size={16} className="task-details-stack">
          <div className="settings-session-list" aria-label="Информация о текущей сессии">
            <SessionRow label="Пользователь" value={displayName} />
            <SessionRow label="Роли" value={roles} />
            <SessionRow label="Источник входа" value={auth.authSource} />
            <SessionRow label="Чаты" value={String(auth.availableChats.length)} />
          </div>
          <Button onClick={auth.logout}>Выйти</Button>
        </Space>
      </Card>

      <Card className="settings-card" title="Названия чатов">
        <Space direction="vertical" size={16} className="task-details-stack">
          <Typography.Text type="secondary">
            Если название чата не подтянулось из MAX, задайте удобное название здесь. Оно будет
            использоваться только в Дьяке.
          </Typography.Text>
          {chatAliasError ? <Alert type="error" showIcon message={chatAliasError} /> : null}
          {editableChats.length > 0 ? (
            <List
              dataSource={editableChats}
              renderItem={(chat) => (
                <List.Item>
                  <Space direction="vertical" size={8} className="task-details-stack">
                    <Space direction="vertical" size={2}>
                      <Typography.Text strong>{getChatDisplayTitle({ chat })}</Typography.Text>
                      <Typography.Text type="secondary">Название в Дьяке</Typography.Text>
                    </Space>
                    <Space.Compact className="settings-chat-alias-control">
                      <Input
                        value={chatAliasValues[chat.id] ?? ""}
                        placeholder="Например: Отдел кадров"
                        maxLength={255}
                        onChange={(event) =>
                          setChatAliasValues((current) => ({
                            ...current,
                            [chat.id]: event.target.value,
                          }))
                        }
                      />
                      <Button
                        type="primary"
                        loading={Boolean(chatAliasSaving[chat.id])}
                        onClick={() => {
                          void saveChatAlias(chat);
                        }}
                      >
                        Сохранить
                      </Button>
                    </Space.Compact>
                  </Space>
                </List.Item>
              )}
            />
          ) : (
            <Typography.Text type="secondary">
              Редактирование названий доступно администратору чата или супер-админу.
            </Typography.Text>
          )}
        </Space>
      </Card>

      <Card className="settings-card">
        <Space direction="vertical" size={16} className="task-details-stack">
          <Typography.Text>
            Сейчас основные действия доступны через Задачи и карточку задачи. Здесь будут собраны
            пользовательские параметры, уведомления и интеграции.
          </Typography.Text>
          <List
            dataSource={plannedSections}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<span className="settings-list-icon">{item.icon}</span>}
                  title={
                    <span className="settings-list-title">
                      <span>{item.title}</span>
                      <Tag>скоро</Tag>
                    </span>
                  }
                  description={item.description}
                />
              </List.Item>
            )}
          />
        </Space>
      </Card>
    </main>
  );
}

function settingsDisplayTitle(settings: Record<string, unknown> | null | undefined): string | null {
  const value = settings?.display_title;
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

function SessionRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="settings-session-row">
      <Typography.Text className="settings-session-label" type="secondary">
        {label}:
      </Typography.Text>
      <div className="settings-session-value">{value}</div>
    </div>
  );
}
