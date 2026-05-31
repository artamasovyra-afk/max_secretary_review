import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  DatePicker,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  notification,
} from "antd";
import type { TableColumnsType } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { getChatMembers, getChats } from "../api/chats";
import { getOrganizations } from "../api/organizations";
import { createGroupAssignment, getTasks } from "../api/tasks";
import { getUsers } from "../api/users";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { TaskStatusTag } from "../components/TaskStatusTag";
import type { Chat, ChatMember } from "../types/chat";
import type { Organization } from "../types/organization";
import type { Task, TaskGroupAssignmentCreatePayload, TaskStatus } from "../types/task";
import type { User } from "../types/user";
import { getChatDisplayTitle } from "../utils/chatDisplayTitle";

interface GroupAssignmentFilters {
  chatId: string;
  status: TaskStatus | "";
}

interface GroupAssignmentFormValues {
  organization_id?: string;
  chat_id: string;
  title: string;
  description?: string;
  deadline_at?: { toISOString: () => string } | null;
  assignee_ids?: string[];
  response_required: boolean;
  exclude_creator: boolean;
}

const initialFilters: GroupAssignmentFilters = {
  chatId: "",
  status: "",
};

const statusOptions: Array<{ label: string; value: TaskStatus }> = [
  { label: "Новая", value: "new" },
  { label: "В работе", value: "in_progress" },
  { label: "Ожидает ответа", value: "waiting_response" },
  { label: "Ожидает приемки", value: "waiting_acceptance" },
  { label: "Выполнена", value: "done" },
  { label: "Просрочена", value: "overdue" },
  { label: "Отклонена", value: "rejected" },
  { label: "Отменена", value: "cancelled" },
];
const futureDeadlineMessage = "Срок должен быть в будущем.";

export function GroupAssignmentsPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [form] = Form.useForm<GroupAssignmentFormValues>();
  const selectedOrganizationId = Form.useWatch("organization_id", form);
  const selectedChatId = Form.useWatch("chat_id", form);
  const excludeCreator = Form.useWatch("exclude_creator", form);
  const selectedAssigneeIds = Form.useWatch("assignee_ids", form) ?? [];
  const [notificationApi, notificationContextHolder] = notification.useNotification();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [chatMembers, setChatMembers] = useState<ChatMember[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [filters, setFilters] = useState<GroupAssignmentFilters>(initialFilters);
  const [loading, setLoading] = useState(false);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [usersLoading, setUsersLoading] = useState(false);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const defaultOrganizationId = auth.organizationId ?? organizations[0]?.id;
  const effectiveSelectedOrganizationId = selectedOrganizationId ?? defaultOrganizationId;
  const showOrganizationSelect = organizations.length > 1;
  const chatById = useMemo(() => new Map(chats.map((chat) => [chat.id, chat])), [chats]);
  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const isSuperAdmin = auth.roles.includes("super_admin");
  const adminChatIds = useMemo(
    () =>
      new Set(
        auth.availableChats
          .filter((chat) => chat.role === "chat_admin" || chat.role === "super_admin")
          .map((chat) => chat.id),
      ),
    [auth.availableChats],
  );
  const canAccessGroupAssignments = isSuperAdmin || adminChatIds.size > 0;
  const eligibleChats = useMemo(
    () => chats.filter((chat) => isGroupAssignmentChat(chat) && (isSuperAdmin || adminChatIds.has(chat.id))),
    [adminChatIds, chats, isSuperAdmin],
  );
  const eligibleChatIds = useMemo(() => new Set(eligibleChats.map((chat) => chat.id)), [eligibleChats]);
  const canCreateChatTask = canAccessGroupAssignments && eligibleChats.length > 0;
  const activeChatMembers = useMemo(
    () => chatMembers.filter((member) => member.is_active),
    [chatMembers],
  );
  const assignableMembers = useMemo(
    () =>
      activeChatMembers.filter((member) => {
        if (!excludeCreator || !auth.userId) {
          return true;
        }
        return member.user_id !== auth.userId;
      }),
    [activeChatMembers, auth.userId, excludeCreator],
  );
  const assignableMemberIds = useMemo(
    () => assignableMembers.map((member) => member.user_id),
    [assignableMembers],
  );
  const participantOptions = useMemo(
    () =>
      assignableMembers.map((member) => ({
        label: participantLabel(member, userById.get(member.user_id), auth.userId ?? undefined),
        value: member.user_id,
      })),
    [assignableMembers, auth.userId, userById],
  );

  const loadAssignments = useCallback(() => {
    setLoading(true);
    setError(null);

    getTasks({
      chat_id: filters.chatId,
      status: filters.status,
      limit: 100,
    })
      .then((nextTasks) => {
        setTasks(nextTasks.filter((task) => task.task_type === "group_assignment"));
      })
      .catch((requestError: unknown) => {
        setTasks([]);
        setError(requestError instanceof Error ? requestError.message : "Не удалось загрузить задачи участникам чата");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [filters.chatId, filters.status]);

  useEffect(() => {
    loadAssignments();
  }, [loadAssignments]);

  useEffect(() => {
    setOptionsLoading(true);
    Promise.all([getChats(), getOrganizations()])
      .then(([nextChats, nextOrganizations]) => {
        setChats(nextChats);
        setOrganizations(nextOrganizations);
      })
      .catch(() => {
        setChats([]);
        setOrganizations([]);
      })
      .finally(() => {
        setOptionsLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!canAccessGroupAssignments) {
      setUsers([]);
      return;
    }

    setUsersLoading(true);
    getUsers()
      .then(setUsers)
      .catch(() => {
        setUsers([]);
      })
      .finally(() => {
        setUsersLoading(false);
      });
  }, [canAccessGroupAssignments]);

  useEffect(() => {
    if (!createModalOpen || !selectedChatId) {
      setChatMembers([]);
      setMembersError(null);
      return;
    }

    let active = true;
    setMembersLoading(true);
    setMembersError(null);
    setChatMembers([]);
    form.setFieldValue("assignee_ids", []);

    getChatMembers(selectedChatId)
      .then((members) => {
        if (!active) {
          return;
        }
        setChatMembers(members.filter((member) => member.is_active));
      })
      .catch((requestError: unknown) => {
        if (!active) {
          return;
        }
        setChatMembers([]);
        setMembersError(requestError instanceof Error ? requestError.message : "Не удалось загрузить участников чата");
      })
      .finally(() => {
        if (active) {
          setMembersLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [createModalOpen, form, selectedChatId]);

  useEffect(() => {
    if (!excludeCreator || !auth.userId) {
      return;
    }

    const currentAssigneeIds = form.getFieldValue("assignee_ids") ?? [];
    if (!currentAssigneeIds.includes(auth.userId)) {
      return;
    }
    form.setFieldValue(
      "assignee_ids",
      currentAssigneeIds.filter((userId: string) => userId !== auth.userId),
    );
  }, [auth.userId, excludeCreator, form]);

  const kpis = useMemo(
    () => ({
      total: tasks.length,
      done: tasks.filter((task) => task.status === "done").length,
      pending: tasks.filter((task) => task.status !== "done" && task.status !== "cancelled").length,
      overdue: tasks.filter((task) => task.status === "overdue").length,
    }),
    [tasks],
  );

  const organizationOptions = useMemo(
    () =>
      organizations.map((organization) => ({
        label: getOrganizationDisplayName(organization),
        value: organization.id,
      })),
    [organizations],
  );

  const chatOptions = useMemo(
    () =>
      eligibleChats
        .filter((chat) => !effectiveSelectedOrganizationId || chat.organization_id === effectiveSelectedOrganizationId)
        .map((chat) => ({
          label: getChatDisplayTitle({ chat }),
          value: chat.id,
        })),
    [effectiveSelectedOrganizationId, eligibleChats],
  );

  const filterChatOptions = useMemo(
    () =>
      eligibleChats.map((chat) => ({
        label: getChatDisplayTitle({ chat }),
        value: chat.id,
      })),
    [eligibleChats],
  );

  const columns = useMemo<TableColumnsType<Task>>(
    () => [
      {
        title: "Задача",
        dataIndex: "title",
        key: "title",
        width: 280,
        render: (title: string, task) => (
          <Space className="tasks-title-cell" direction="vertical" size={2}>
            <Typography.Text className="tasks-title-text" strong ellipsis={{ tooltip: title }}>
              {title}
            </Typography.Text>
            <Typography.Text className="tasks-id-text" type="secondary">
              {task.task_ref}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: "Постановщик",
        key: "creator",
        width: 210,
        render: (_, task) => (
          <Space direction="vertical" size={2}>
            <Typography.Text ellipsis={{ tooltip: creatorLabel(task) }}>{creatorLabel(task)}</Typography.Text>
            <Typography.Text type="secondary">{roleLabel(task.creator_role_snapshot)}</Typography.Text>
          </Space>
        ),
      },
      {
        title: "Чат",
        key: "chat",
        width: 190,
        render: (_, task) => (
          <Typography.Text ellipsis={{ tooltip: chatLabel(task, chatById.get(task.chat_id)) }}>
            {chatLabel(task, chatById.get(task.chat_id))}
          </Typography.Text>
        ),
      },
      {
        title: "Статус",
        dataIndex: "status",
        key: "status",
        width: 145,
        render: (status: Task["status"]) => <TaskStatusTag status={status} />,
      },
      {
        title: "Срок",
        dataIndex: "deadline_at",
        key: "deadline_at",
        width: 150,
        render: (deadlineAt: string | null, task) => formatDeadline(deadlineAt, task.status),
      },
      {
        title: "Отчет",
        dataIndex: "requires_individual_report",
        key: "report",
        width: 150,
        render: (requiresReport: boolean) =>
          requiresReport ? <Tag color="blue">Обязательный</Tag> : <Tag>Не требуется</Tag>,
      },
      {
        title: "Действия",
        key: "actions",
        width: 110,
        align: "right",
        render: (_, task) => (
          <Button type="link" size="small" onClick={() => navigate(auth.withAuthSearch(`/group-assignments/${task.id}`))}>
            Отчет
          </Button>
        ),
      },
    ],
    [auth, chatById, navigate],
  );

  useEffect(() => {
    if (!createModalOpen || !defaultOrganizationId || form.getFieldValue("organization_id")) {
      return;
    }
    form.setFieldValue("organization_id", defaultOrganizationId);
  }, [createModalOpen, defaultOrganizationId, form]);

  const openCreateModal = () => {
    const defaultChatId = auth.chatId && eligibleChatIds.has(auth.chatId) ? auth.chatId : eligibleChats[0]?.id;
    form.resetFields();
    form.setFieldsValue({
      organization_id: defaultOrganizationId,
      chat_id: defaultChatId,
      assignee_ids: [],
      response_required: true,
      exclude_creator: true,
    });
    setChatMembers([]);
    setMembersError(null);
    setCreateModalOpen(true);

    if (chats.length > 0 && organizations.length > 0 && (!canAccessGroupAssignments || users.length > 0)) {
      return;
    }

    setOptionsLoading(true);
    Promise.all([getChats(), getOrganizations()])
      .then(([nextChats, nextOrganizations]) => {
        setChats(nextChats);
        setOrganizations(nextOrganizations);
      })
      .catch((requestError: unknown) => {
        notificationApi.error({
          message: "Не удалось загрузить данные формы",
          description: requestError instanceof Error ? requestError.message : "Попробуйте открыть форму позже",
        });
      })
      .finally(() => {
        setOptionsLoading(false);
      });

    if (canAccessGroupAssignments && users.length === 0) {
      setUsersLoading(true);
      getUsers()
        .then(setUsers)
        .catch(() => {
          setUsers([]);
        })
        .finally(() => {
          setUsersLoading(false);
        });
    }
  };

  const selectAllParticipants = () => {
    form.setFieldValue("assignee_ids", assignableMemberIds);
  };

  const clearParticipants = () => {
    form.setFieldValue("assignee_ids", []);
  };

  const submitCreate = async () => {
    if (!auth.userId) {
      notificationApi.warning({
        message: "Пользователь сессии не определен",
        description: "Откройте WebApp из MAX или обновите страницу, чтобы восстановить доступ.",
      });
      return;
    }

    try {
      const values = await form.validateFields();
      const organizationId = values.organization_id ?? defaultOrganizationId;
      if (!organizationId) {
        notificationApi.warning({
          message: "Не удалось определить организацию",
          description: "Обновите экран и попробуйте создать задачу еще раз.",
        });
        return;
      }
      const payload: TaskGroupAssignmentCreatePayload = {
        organization_id: organizationId,
        chat_id: values.chat_id,
        created_by_user_id: auth.userId,
        title: values.title.trim(),
        description: values.description?.trim() || null,
        deadline_at: values.deadline_at?.toISOString() ?? null,
        assignee_ids: values.assignee_ids ?? [],
        response_required: values.response_required,
        exclude_creator: values.exclude_creator,
      };

      setSubmitting(true);
      const result = await createGroupAssignment(payload);
      notificationApi.success({
        message: "Задача участникам чата создана",
        description: `${result.task_ref}: ${payload.title}. Исполнителей: ${result.total_assignees}`,
        btn: (
          <Button size="small" onClick={() => navigate(auth.withAuthSearch("/group-assignments"))}>
            К задачам
          </Button>
        ),
      });
      setCreateModalOpen(false);
      form.resetFields();
      loadAssignments();
      navigate(auth.withAuthSearch(`/group-assignments/${result.task_id}`));
    } catch (requestError) {
      if (typeof requestError === "object" && requestError !== null && "errorFields" in requestError) {
        return;
      }

      notificationApi.error({
        message: "Не удалось создать задачу участникам чата",
        description: friendlyError(requestError),
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (auth.userId && !canAccessGroupAssignments) {
    return (
      <main className="page">
        <div className="page-heading tasks-page-heading">
          <Space direction="vertical" size={4}>
            <Typography.Title level={2}>Задача участникам чата</Typography.Title>
            <Typography.Text type="secondary">Создание задач участникам доступно администраторам чатов.</Typography.Text>
          </Space>
          <Button onClick={() => navigate(auth.withAuthSearch("/tasks"))}>К задачам</Button>
        </div>
        <Alert
          className="tasks-alert"
          type="warning"
          showIcon
          message="Это действие доступно администратору чата."
          description="Создать задачу участникам можно только в активных чатах, где у вас есть роль админа чата."
        />
      </main>
    );
  }

  return (
    <main className="page">
      {notificationContextHolder}
      <div className="page-heading tasks-page-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={2}>Задача участникам чата</Typography.Title>
          <Typography.Text type="secondary">
            Создавайте задачи участникам выбранного чата с индивидуальным отчетом
          </Typography.Text>
        </Space>
        <Space wrap>
          {canAccessGroupAssignments ? (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!auth.userId || optionsLoading || !canCreateChatTask}
              onClick={openCreateModal}
            >
              Создать задачу
            </Button>
          ) : null}
          <Button icon={<ReloadOutlined />} onClick={loadAssignments}>
            Обновить
          </Button>
        </Space>
      </div>

      {!auth.userId ? (
        <Alert
          className="tasks-alert"
          type="info"
          showIcon
          message="Создание задач участникам чата требует авторизации"
          description="Откройте WebApp из MAX. Права на создание таких задач определяются по вашей сессии и роли в чате."
        />
      ) : null}

      {auth.userId && canAccessGroupAssignments && !optionsLoading && !canCreateChatTask ? (
        <Alert
          className="tasks-alert"
          type="info"
          showIcon
          message="Нет доступных активных чатов для групповой задачи."
          description="Нужен подключенный active-чат с вашей ролью админа чата. Отключенные или неподключенные чаты здесь не используются."
        />
      ) : null}

      <section className="tasks-kpi-grid" aria-label="Сводные показатели задач участникам чата">
        <Card className="tasks-kpi-card" size="small">
          <Statistic title="Всего" value={kpis.total} />
        </Card>
        <Card className="tasks-kpi-card" size="small">
          <Statistic title="Выполнены" value={kpis.done} valueStyle={{ color: "#16a34a" }} />
        </Card>
        <Card className="tasks-kpi-card" size="small">
          <Statistic title="Ожидают" value={kpis.pending} valueStyle={{ color: "#2563eb" }} />
        </Card>
        <Card className="tasks-kpi-card" size="small">
          <Statistic title="Просрочено" value={kpis.overdue} valueStyle={{ color: "#dc2626" }} />
        </Card>
      </section>

      <Space className="tasks-filters" size={[8, 8]} wrap>
        <Select
          allowClear
          className="tasks-filter-id"
          options={filterChatOptions}
          placeholder="Чат"
          value={filters.chatId || undefined}
          onChange={(value) => setFilters((current) => ({ ...current, chatId: value ?? "" }))}
        />
        <Select
          allowClear
          className="tasks-filter-status"
          options={statusOptions}
          placeholder="Статус"
          value={filters.status || undefined}
          onChange={(value) => setFilters((current) => ({ ...current, status: value ?? "" }))}
        />
        <Button onClick={() => setFilters(initialFilters)}>Сбросить</Button>
      </Space>

      {error ? (
        <Alert
          className="tasks-alert"
          type="error"
          showIcon
          message="Не удалось загрузить задачи участникам чата"
          description={friendlyError(error)}
          action={
            <Button size="small" onClick={loadAssignments}>
              Повторить
            </Button>
          }
        />
      ) : null}

      <div className="tasks-table-shell">
        <Spin spinning={loading} tip="Загрузка задач участникам чата">
          <Table<Task>
            rowKey="id"
            columns={columns}
            dataSource={error ? [] : tasks}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            scroll={{ x: 1135 }}
            size="small"
            locale={{
              emptyText: (
                <Empty
                  description={
                    <Space direction="vertical" size={4}>
                      <Typography.Text>Задач участникам чата пока нет</Typography.Text>
                      <Typography.Text type="secondary">
                        Создайте задачу для участников конкретного чата.
                      </Typography.Text>
                    </Space>
                  }
                >
                  {canCreateChatTask ? (
                    <Button type="primary" icon={<PlusOutlined />} disabled={!auth.userId} onClick={openCreateModal}>
                      Создать задачу
                    </Button>
                  ) : null}
                </Empty>
              ),
            }}
          />
        </Spin>
      </div>

      <Modal
        title="Новая задача участникам"
        className="task-action-modal group-assignment-modal"
        open={createModalOpen}
        okText="Создать"
        cancelText="Отмена"
        confirmLoading={submitting}
        onCancel={() => {
          if (!submitting) {
            setCreateModalOpen(false);
          }
        }}
        onOk={submitCreate}
        width={760}
      >
        <Form<GroupAssignmentFormValues>
          form={form}
          layout="vertical"
          className="task-create-form"
          initialValues={{
            response_required: true,
            exclude_creator: true,
          }}
        >
          {showOrganizationSelect ? (
            <Form.Item
              label="Организация"
              name="organization_id"
              rules={[{ required: true, message: "Выберите организацию" }]}
            >
              <Select
                showSearch
                loading={optionsLoading}
                optionFilterProp="label"
                options={organizationOptions}
                placeholder="Выберите организацию"
                onChange={() => {
                  form.setFieldsValue({ chat_id: undefined, assignee_ids: [] });
                  setChatMembers([]);
                  setMembersError(null);
                }}
              />
            </Form.Item>
          ) : (
            <Form.Item name="organization_id" hidden>
              <Input type="hidden" />
            </Form.Item>
          )}

          <Form.Item label="Чат" name="chat_id" rules={[{ required: true, message: "Выберите чат" }]}>
            <Select
              showSearch
              loading={optionsLoading}
              optionFilterProp="label"
              options={chatOptions}
              placeholder="Выберите чат"
              onChange={() => {
                form.setFieldValue("assignee_ids", []);
              }}
            />
          </Form.Item>

          <Form.Item name="exclude_creator" valuePropName="checked" noStyle>
            <Checkbox className="group-assignment-exclude-checkbox">Не назначать постановщику</Checkbox>
          </Form.Item>

          <Form.Item
            label="Исполнители"
            name="assignee_ids"
            rules={[{ validator: validateAssignees }]}
            extra={
              selectedChatId
                ? "Выберите активных участников выбранного чата. Список сбрасывается при смене чата."
                : "Сначала выберите чат."
            }
          >
            <Select
              allowClear
              showSearch
              mode="multiple"
              disabled={!selectedChatId || membersLoading || Boolean(membersError)}
              loading={membersLoading || usersLoading}
              maxTagCount="responsive"
              optionFilterProp="label"
              options={participantOptions}
              placeholder={selectedChatId ? "Выберите исполнителей" : "Выберите чат"}
            />
          </Form.Item>

          <div className="group-assignment-member-toolbar">
            <Space size={[8, 8]} wrap>
              <Button
                size="small"
                disabled={!selectedChatId || membersLoading || assignableMemberIds.length === 0}
                onClick={selectAllParticipants}
              >
                Выбрать всех
              </Button>
              <Button size="small" disabled={selectedAssigneeIds.length === 0} onClick={clearParticipants}>
                Снять всех
              </Button>
              <Typography.Text type="secondary">
                Выбрано: {selectedAssigneeIds.length} из {assignableMemberIds.length}
              </Typography.Text>
            </Space>
          </div>

          {membersError ? (
            <Alert
              className="tasks-alert"
              type="error"
              showIcon
              message="Не удалось загрузить участников чата"
              description={friendlyError(membersError)}
            />
          ) : null}

          {selectedChatId && !membersLoading && assignableMemberIds.length === 0 ? (
            <Alert
              className="tasks-alert"
              type="warning"
              showIcon
              message="Некого назначить"
              description={
                excludeCreator
                  ? "Некого назначить: в чате нет других активных участников."
                  : "В выбранном чате нет активных участников для назначения."
              }
            />
          ) : null}

          <Form.Item
            label="Текст задачи"
            name="title"
            rules={[{ required: true, whitespace: true, message: "Введите текст задачи" }]}
          >
            <Input placeholder="Что нужно сделать?" />
          </Form.Item>

          <Form.Item label="Описание" name="description">
            <Input.TextArea rows={3} placeholder="Контекст, детали, ожидаемый отчет" />
          </Form.Item>

          <Form.Item
            label="Срок"
            name="deadline_at"
            rules={[{ required: true, message: "Укажите срок" }, { validator: validateFutureDeadline }]}
          >
            <DatePicker
              showTime
              showNow
              format="DD.MM.YYYY HH:mm"
              popupClassName="mobile-safe-picker-dropdown"
              placement="bottomLeft"
              placeholder="Выберите дату и время"
            />
          </Form.Item>

          <Space direction="vertical" size={6}>
            <Form.Item name="response_required" valuePropName="checked" noStyle>
              <Checkbox>Обязательный отчет</Checkbox>
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </main>
  );
}

function creatorLabel(task: Task): string {
  return task.creator_display_name_snapshot || "Пользователь";
}

function chatLabel(task: Task, chat: Chat | undefined): string {
  return getChatDisplayTitle({
    chat,
    sourceTitle: task.source_chat_title_snapshot,
  });
}

function getOrganizationDisplayName(organization: Organization): string {
  const name = organization.name.trim();
  if (!name || /^max default organization\b/i.test(name)) {
    return "Основная организация";
  }
  return name;
}

function roleLabel(role: string | null): string {
  const labels: Record<string, string> = {
    chat_admin: "Админ чата",
    member: "Участник",
    super_admin: "Суперадмин",
  };
  return role ? labels[role] ?? role : "Роль не указана";
}

function participantLabel(member: ChatMember, user: User | undefined, currentUserId: string | undefined): string {
  const parts = [displayUserName(user), roleLabel(member.role)];
  if (currentUserId && member.user_id === currentUserId) {
    parts.push("вы");
  }
  return parts.join(" · ");
}

function displayUserName(user: User | undefined): string {
  const displayName = user?.display_name?.trim();
  if (displayName) {
    return displayName;
  }
  const username = user?.username?.trim();
  if (username) {
    return `@${username}`;
  }
  return "Участник чата";
}

function isGroupAssignmentChat(chat: Chat): boolean {
  return chat.status === "active" && Boolean(chat.max_chat_id);
}

function formatDeadline(value: string | null, status: TaskStatus) {
  if (!value) {
    return <Tag>Без срока</Tag>;
  }

  const text = new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));

  if (status !== "overdue") {
    return <Tag>{text}</Tag>;
  }

  return (
    <Tag className="tasks-deadline-overdue" color="default">
      {text}
    </Tag>
  );
}

function friendlyError(error: unknown): string {
  if (error instanceof ApiError && error.details && typeof error.details === "object") {
    const detail = (error.details as { detail?: unknown }).detail;
    if (detail === "deadline_must_be_in_future") {
      return futureDeadlineMessage;
    }
    if (detail === "deadline_required") {
      return "Укажите срок задачи.";
    }
    if (detail === "no_assignees") {
      return "Выберите хотя бы одного исполнителя.";
    }
    if (detail === "assignee_not_in_chat") {
      return "Выбранный исполнитель не состоит в этом чате.";
    }
    if (detail === "chat_not_active" || detail === "inactive_chat") {
      return "Чат не подключен или отключен.";
    }
    if (detail === "insufficient_permissions") {
      return "Недостаточно прав.";
    }
  }
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return "Недостаточно прав.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "Проверьте данные и повторите попытку";
}

function validateAssignees(_rule: unknown, value?: string[]): Promise<void> {
  if (value && value.length > 0) {
    return Promise.resolve();
  }
  return Promise.reject(new Error("Выберите хотя бы одного исполнителя."));
}

function validateFutureDeadline(_rule: unknown, value?: { toISOString: () => string } | null): Promise<void> {
  if (!value) {
    return Promise.resolve();
  }
  const deadlineAt = Date.parse(value.toISOString());
  if (Number.isNaN(deadlineAt) || deadlineAt < Date.now() + 60_000) {
    return Promise.reject(new Error(futureDeadlineMessage));
  }
  return Promise.resolve();
}
