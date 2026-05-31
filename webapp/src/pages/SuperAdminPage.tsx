import {
  CheckCircleOutlined,
  LogoutOutlined,
  PauseCircleOutlined,
  SafetyOutlined,
  StopOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Empty,
  Form,
  Input,
  List,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  notification,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getSuperAdminChatMembers,
  getSuperAdminChats,
  getSuperAdminSession,
  loginSuperAdmin,
  logoutSuperAdmin,
  syncSuperAdminChatMaxInfo,
  syncSuperAdminChatMaxAdmins,
  updateSuperAdminChatDisplayTitle,
  updateSuperAdminChatMemberRole,
  updateSuperAdminChatSettings,
  updateSuperAdminChatStatus,
} from "../api/superAdmin";
import type {
  SuperAdminChat,
  SuperAdminChatMember,
  SuperAdminChatStatus,
  SuperAdminSession,
} from "../types/superAdmin";

const statusLabels: Record<SuperAdminChatStatus, string> = {
  pending_approval: "Ожидает подключения",
  active: "Подключен",
  rejected: "Отклонен",
  suspended: "Отключен",
};

const statusFilterOptions: Array<{ label: string; value: SuperAdminChatStatus | "all" }> = [
  { label: "Все", value: "all" },
  { label: "Ожидают подключения", value: "pending_approval" },
  { label: "Подключены", value: "active" },
  { label: "Отклонены", value: "rejected" },
  { label: "Отключены", value: "suspended" },
];

export function SuperAdminPage() {
  const [notificationApi, notificationContextHolder] = notification.useNotification();
  const [session, setSession] = useState<SuperAdminSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginSubmitting, setLoginSubmitting] = useState(false);
  const [chats, setChats] = useState<SuperAdminChat[]>([]);
  const [membersByChat, setMembersByChat] = useState<Record<string, SuperAdminChatMember[]>>({});
  const [membersLoading, setMembersLoading] = useState<Record<string, boolean>>({});
  const [maxRolesSyncing, setMaxRolesSyncing] = useState<Record<string, boolean>>({});
  const [chatInfoSyncing, setChatInfoSyncing] = useState<Record<string, boolean>>({});
  const [titleDrafts, setTitleDrafts] = useState<Record<string, string>>({});
  const [titleSaving, setTitleSaving] = useState<Record<string, boolean>>({});
  const [settingsSaving, setSettingsSaving] = useState<Record<string, boolean>>({});
  const [chatsLoading, setChatsLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<SuperAdminChatStatus | "all">("all");
  const [search, setSearch] = useState("");

  const loadChats = useCallback((status: SuperAdminChatStatus | "all") => {
    setChatsLoading(true);
    getSuperAdminChats(status)
      .then((items) => {
        setChats(items);
        setTitleDrafts((current) => {
          const next = { ...current };
          for (const chat of items) {
            if (!(chat.id in next)) {
              next[chat.id] = chat.display_title_source === "manual" ? chat.display_title : "";
            }
          }
          return next;
        });
      })
      .catch((error: unknown) => {
        notificationApi.error({
          message: "Не удалось загрузить чаты",
          description: error instanceof Error ? error.message : "Проверьте доступ и попробуйте еще раз.",
        });
      })
      .finally(() => {
        setChatsLoading(false);
      });
  }, [notificationApi]);

  useEffect(() => {
    getSuperAdminSession()
      .then((nextSession) => {
        setSession(nextSession);
      })
      .catch(() => {
        setSession(null);
      })
      .finally(() => {
        setSessionLoading(false);
      });
  }, []);

  useEffect(() => {
    if (session) {
      loadChats(statusFilter);
    }
  }, [loadChats, session, statusFilter]);

  const filteredChats = useMemo(() => {
    const query = search.trim().toLowerCase();
    return chats.filter((chat) => {
      const matchesStatus = statusFilter === "all" || chat.status === statusFilter;
      const matchesSearch = !query || chat.display_title.toLowerCase().includes(query);
      return matchesStatus && matchesSearch;
    });
  }, [chats, search, statusFilter]);

  const handleLogin = async (values: { login: string; password: string }) => {
    setLoginSubmitting(true);
    setLoginError(null);
    try {
      const nextSession = await loginSuperAdmin({
        login: values.login.trim(),
        password: values.password.trim(),
      });
      setSession(nextSession);
    } catch (error: unknown) {
      setLoginError(error instanceof Error ? error.message : "Не удалось войти.");
    } finally {
      setLoginSubmitting(false);
    }
  };

  const handleLogout = async () => {
    await logoutSuperAdmin();
    setSession(null);
    setChats([]);
    setMembersByChat({});
    setTitleDrafts({});
  };

  const loadMembers = (chatId: string, force = false) => {
    if (!force && (membersByChat[chatId] || membersLoading[chatId])) {
      return;
    }
    setMembersLoading((current) => ({ ...current, [chatId]: true }));
    getSuperAdminChatMembers(chatId)
      .then((members) => {
        setMembersByChat((current) => ({ ...current, [chatId]: members }));
      })
      .catch((error: unknown) => {
        notificationApi.error({
          message: "Не удалось загрузить участников",
          description: error instanceof Error ? error.message : "Попробуйте еще раз.",
        });
      })
      .finally(() => {
        setMembersLoading((current) => ({ ...current, [chatId]: false }));
      });
  };

  const changeStatus = async (chat: SuperAdminChat, status: SuperAdminChatStatus) => {
    if (status === "active" && isFallbackChatTitle(chat)) {
      const confirmed = window.confirm("У чата не задано название. Рекомендуем указать название перед подключением.");
      if (!confirmed) {
        return;
      }
    }
    const updated = await updateSuperAdminChatStatus(chat.id, status);
    setChats((current) => current.map((item) => (item.id === chat.id ? updated : item)));
    notificationApi.success({ message: "Статус чата обновлен", description: updated.display_title });
  };

  const saveDisplayTitle = async (chat: SuperAdminChat) => {
    const value = (titleDrafts[chat.id] ?? "").trim();
    setTitleSaving((current) => ({ ...current, [chat.id]: true }));
    try {
      const updated = await updateSuperAdminChatDisplayTitle(chat.id, value || null);
      setChats((current) => current.map((item) => (item.id === chat.id ? updated : item)));
      setTitleDrafts((current) => ({
        ...current,
        [chat.id]: updated.display_title_source === "manual" ? updated.display_title : "",
      }));
      notificationApi.success({ message: "Название чата сохранено", description: updated.display_title });
    } catch (error: unknown) {
      notificationApi.error({
        message: "Не удалось сохранить название",
        description: error instanceof Error ? error.message : "Проверьте доступ и попробуйте еще раз.",
      });
    } finally {
      setTitleSaving((current) => ({ ...current, [chat.id]: false }));
    }
  };

  const toggleDeadlineReminders = async (chat: SuperAdminChat, enabled: boolean) => {
    if (chat.status !== "active") {
      return;
    }
    setSettingsSaving((current) => ({ ...current, [chat.id]: true }));
    try {
      const updated = await updateSuperAdminChatSettings(chat.id, {
        deadline_reminders_enabled: enabled,
      });
      setChats((current) => current.map((item) => (item.id === chat.id ? updated : item)));
      notificationApi.success({
        message: enabled ? "Дедлайн-уведомления включены" : "Дедлайн-уведомления выключены",
        description: updated.display_title,
      });
    } catch (error: unknown) {
      notificationApi.error({
        message: "Не удалось обновить дедлайн-уведомления",
        description: error instanceof Error ? error.message : "Проверьте состояние чата и попробуйте снова.",
      });
    } finally {
      setSettingsSaving((current) => ({ ...current, [chat.id]: false }));
    }
  };

  const syncChatInfo = async (chat: SuperAdminChat) => {
    setChatInfoSyncing((current) => ({ ...current, [chat.id]: true }));
    try {
      const result = await syncSuperAdminChatMaxInfo(chat.id);
      loadChats(statusFilter);
      if (result.title_updated) {
        notificationApi.success({ message: "Название обновлено из MAX", description: result.display_title });
      } else if (result.title_source === "fallback") {
        notificationApi.warning({
          message: "MAX не передал название",
          description: "Укажите название вручную перед подключением чата.",
        });
      } else {
        notificationApi.info({ message: "Название уже задано", description: result.display_title });
      }
    } catch (error: unknown) {
      notificationApi.error({
        message: "Не удалось обновить название из MAX",
        description: error instanceof Error ? error.message : "Укажите название вручную.",
      });
    } finally {
      setChatInfoSyncing((current) => ({ ...current, [chat.id]: false }));
    }
  };

  const syncMaxRoles = async (chat: SuperAdminChat) => {
    setMaxRolesSyncing((current) => ({ ...current, [chat.id]: true }));
    try {
      const result = await syncSuperAdminChatMaxAdmins(chat.id);
      const refreshedMembers = await getSuperAdminChatMembers(chat.id);
      setMembersByChat((current) => ({ ...current, [chat.id]: refreshedMembers }));
      setChats((current) =>
        current.map((item) =>
          item.id === chat.id
            ? {
                ...item,
                max_admins_count: result.max_admins_count,
              }
            : item,
        ),
      );
      notificationApi.success({
        message: "MAX-роли обновлены",
        description: `Проверено участников: ${result.checked_members_count}. Админов MAX: ${result.max_admins_count}.`,
      });
    } catch (error: unknown) {
      notificationApi.error({
        message: "Не удалось проверить роли MAX",
        description: error instanceof Error ? error.message : "Попробуйте позже.",
      });
    } finally {
      setMaxRolesSyncing((current) => ({ ...current, [chat.id]: false }));
    }
  };

  const toggleChatAdmin = async (chat: SuperAdminChat, member: SuperAdminChatMember, checked: boolean) => {
    const role = checked ? "chat_admin" : "member";
    const allowRemoveLastAdmin =
      !checked && chat.chat_admins_count <= 1
        ? window.confirm("Это последний админ чата в Дьяке. Снять роль все равно?")
        : false;
    if (!checked && chat.chat_admins_count <= 1 && !allowRemoveLastAdmin) {
      return;
    }
    try {
      const updated = await updateSuperAdminChatMemberRole(chat.id, member.user_id, {
        role,
        allow_remove_last_admin: allowRemoveLastAdmin,
      });
      setMembersByChat((current) => ({
        ...current,
        [chat.id]: (current[chat.id] ?? []).map((item) => (item.user_id === member.user_id ? updated : item)),
      }));
      setChats((current) =>
        current.map((item) =>
          item.id === chat.id
            ? {
                ...item,
                chat_admins_count: Math.max(0, item.chat_admins_count + (checked ? 1 : -1)),
              }
            : item,
        ),
      );
      notificationApi.success({ message: "Роль участника обновлена", description: member.display_name });
    } catch (error: unknown) {
      notificationApi.error({
        message: "Не удалось обновить роль",
        description: error instanceof Error ? error.message : "Проверьте состояние чата и попробуйте снова.",
      });
    }
  };

  if (sessionLoading) {
    return (
      <div className="super-admin-auth-state">
        <Spin size="large" />
        <Typography.Text type="secondary">Проверяем вход…</Typography.Text>
      </div>
    );
  }

  if (!session) {
    return (
      <main className="super-admin-shell">
        {notificationContextHolder}
        <Card className="super-admin-login-card">
          <Space direction="vertical" size={18} className="task-details-stack">
            <Space direction="vertical" size={4}>
              <Typography.Title level={2}>Дьяк · Супер-админ</Typography.Title>
              <Typography.Text type="secondary">
                Отдельный вход для подключения чатов и управления администраторами Дьяка.
              </Typography.Text>
            </Space>
            {loginError ? <Alert type="error" showIcon message={loginError} /> : null}
            <Form layout="vertical" onFinish={handleLogin}>
              <Form.Item name="login" label="Логин" rules={[{ required: true, message: "Введите логин" }]}>
                <Input autoComplete="username" />
              </Form.Item>
              <Form.Item name="password" label="Пароль" rules={[{ required: true, message: "Введите пароль" }]}>
                <Input.Password autoComplete="current-password" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loginSubmitting} block>
                Войти
              </Button>
            </Form>
          </Space>
        </Card>
      </main>
    );
  }

  return (
    <main className="super-admin-shell">
      {notificationContextHolder}
      <section className="super-admin-header">
        <Space direction="vertical" size={2}>
          <Typography.Title level={2}>Дьяк · Супер-админ</Typography.Title>
          <Typography.Text type="secondary">Подключение чатов и роли администраторов</Typography.Text>
        </Space>
        <Button icon={<LogoutOutlined />} onClick={() => void handleLogout()}>
          Выйти
        </Button>
      </section>

      <Card className="super-admin-panel">
        <Space className="super-admin-filters" size={12} wrap>
          <Input.Search
            allowClear
            placeholder="Поиск по названию чата"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Select
            value={statusFilter}
            options={statusFilterOptions}
            onChange={(nextStatus) => {
              setSearch("");
              setStatusFilter(nextStatus);
            }}
            className="super-admin-status-select"
          />
          <Button onClick={() => loadChats(statusFilter)} loading={chatsLoading}>
            Обновить
          </Button>
        </Space>
      </Card>

      {chatsLoading ? (
        <div className="super-admin-auth-state">
          <Spin />
          <Typography.Text type="secondary">Загружаем чаты…</Typography.Text>
        </div>
      ) : filteredChats.length === 0 ? (
        <Empty
          description={search.trim() ? "Чаты есть, но скрыты поиском" : "Чатов по этим условиям нет"}
        >
          {search.trim() ? <Button onClick={() => setSearch("")}>Сбросить поиск</Button> : null}
        </Empty>
      ) : (
        <List
          className="super-admin-chat-list"
          dataSource={filteredChats}
          renderItem={(chat) => (
            <List.Item>
              <Card className="super-admin-chat-card">
                <Space direction="vertical" size={14} className="task-details-stack">
                  <div className="super-admin-chat-card-header">
                    <Space direction="vertical" size={4}>
                      <Typography.Title level={4}>{chat.display_title}</Typography.Title>
                      <Space size={8} wrap>
                        <StatusTag status={chat.status} />
                        <Typography.Text type="secondary">Участников: {chat.members_count}</Typography.Text>
                        <Typography.Text type="secondary">Админов Дьяка: {chat.chat_admins_count}</Typography.Text>
                        <Typography.Text type="secondary">
                          Админов MAX: {chat.max_admins_count ?? "не проверено"}
                        </Typography.Text>
                      </Space>
                    </Space>
                    <Space wrap>
                      <Button
                        icon={<CheckCircleOutlined />}
                        onClick={() => void changeStatus(chat, "active")}
                        disabled={chat.status === "active"}
                      >
                        Подключить
                      </Button>
                      <Button
                        icon={<StopOutlined />}
                        onClick={() => void changeStatus(chat, "rejected")}
                        disabled={chat.status === "rejected"}
                      >
                        Отклонить
                      </Button>
                      <Button
                        icon={<PauseCircleOutlined />}
                        onClick={() => void changeStatus(chat, "suspended")}
                        disabled={chat.status === "suspended"}
                      >
                        Отключить
                      </Button>
                    </Space>
                  </div>

                  {chat.status === "pending_approval" && isFallbackChatTitle(chat) ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="У чата не задано название"
                      description="Попробуйте обновить название из MAX или задайте название в Дьяке перед подключением."
                    />
                  ) : null}

                  {chat.status === "pending_approval" ? (
                    <Space direction="vertical" size={8} className="task-details-stack">
                      <Typography.Text type="secondary">Название чата в Дьяке</Typography.Text>
                      <Space.Compact className="settings-chat-alias-control">
                        <Input
                          value={titleDrafts[chat.id] ?? ""}
                          placeholder="Например: Отдел кадров"
                          maxLength={255}
                          onChange={(event) =>
                            setTitleDrafts((current) => ({ ...current, [chat.id]: event.target.value }))
                          }
                        />
                        <Button
                          type="primary"
                          loading={Boolean(titleSaving[chat.id])}
                          onClick={() => void saveDisplayTitle(chat)}
                        >
                          Сохранить название
                        </Button>
                      </Space.Compact>
                      <Button
                        icon={<SyncOutlined />}
                        loading={Boolean(chatInfoSyncing[chat.id])}
                        onClick={() => void syncChatInfo(chat)}
                      >
                        Обновить из MAX
                      </Button>
                    </Space>
                  ) : null}

                  <Tooltip title={chat.status === "active" ? undefined : "Доступно после подключения чата."}>
                    <Space size={12} wrap>
                      <Typography.Text strong>Дедлайн-уведомления</Typography.Text>
                      <Switch
                        checked={chat.deadline_reminders_enabled}
                        checkedChildren="вкл"
                        unCheckedChildren="выкл"
                        disabled={chat.status !== "active"}
                        loading={Boolean(settingsSaving[chat.id])}
                        onChange={(checked) => void toggleDeadlineReminders(chat, checked)}
                      />
                      <Typography.Text type="secondary">
                        {chat.deadline_reminders_enabled ? "включены" : "выключены"}
                      </Typography.Text>
                    </Space>
                  </Tooltip>

                  <Collapse
                    ghost
                    items={[
                      {
                        key: "members",
                        label: "Участники",
                        children: (
                          <MembersList
                            chat={chat}
                            members={membersByChat[chat.id] ?? []}
                            loading={Boolean(membersLoading[chat.id])}
                            syncing={Boolean(maxRolesSyncing[chat.id])}
                            onLoad={() => loadMembers(chat.id)}
                            onSync={() => void syncMaxRoles(chat)}
                            onToggle={(member, checked) => void toggleChatAdmin(chat, member, checked)}
                          />
                        ),
                      },
                    ]}
                    onChange={(keys) => {
                      const activeKeys = Array.isArray(keys) ? keys : [keys];
                      if (activeKeys.includes("members")) {
                        loadMembers(chat.id);
                      }
                    }}
                  />
                </Space>
              </Card>
            </List.Item>
          )}
        />
      )}
    </main>
  );
}

function MembersList({
  chat,
  members,
  loading,
  syncing,
  onLoad,
  onSync,
  onToggle,
}: {
  chat: SuperAdminChat;
  members: SuperAdminChatMember[];
  loading: boolean;
  syncing: boolean;
  onLoad: () => void;
  onSync: () => void;
  onToggle: (member: SuperAdminChatMember, checked: boolean) => void;
}) {
  useEffect(() => {
    onLoad();
  }, [onLoad]);

  if (loading) {
    return <Spin />;
  }
  return (
    <Space direction="vertical" size={12} className="task-details-stack">
      <Button icon={<SyncOutlined />} loading={syncing} onClick={onSync}>
        Обновить роли MAX
      </Button>
      {members.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Участников пока нет" />
      ) : (
        <List
          dataSource={members}
          renderItem={(member) => (
            <List.Item className="super-admin-member-row">
              <Space direction="vertical" size={4}>
                <Typography.Text strong>{member.display_name}</Typography.Text>
                <Space size={8} wrap>
                  <Tag>{member.role_in_dyak === "chat_admin" ? "Админ чата" : "Пользователь"}</Tag>
                  <Tag icon={<SafetyOutlined />}>{maxAdminLabel(member.is_max_chat_admin)}</Tag>
                  {!member.is_active ? <Tag>Отключен</Tag> : null}
                </Space>
              </Space>
              <Checkbox
                checked={member.role_in_dyak === "chat_admin"}
                disabled={member.role_in_dyak === "super_admin" || chat.status === "rejected"}
                onChange={(event) => onToggle(member, event.target.checked)}
              >
                Админ чата в Дьяке
              </Checkbox>
            </List.Item>
          )}
        />
      )}
    </Space>
  );
}

function StatusTag({ status }: { status: SuperAdminChatStatus }) {
  const color =
    status === "active"
      ? "green"
      : status === "pending_approval"
        ? "blue"
        : status === "rejected"
          ? "red"
          : "orange";
  return <Tag color={color}>{statusLabels[status]}</Tag>;
}

function maxAdminLabel(value: boolean | null): string {
  if (value === true) {
    return "Админ в MAX: Да";
  }
  if (value === false) {
    return "Админ в MAX: Нет";
  }
  return "Админ в MAX: Не проверено";
}

function isFallbackChatTitle(chat: SuperAdminChat): boolean {
  return chat.display_title_source === "fallback" || chat.display_title.trim() === "Чат без названия";
}
