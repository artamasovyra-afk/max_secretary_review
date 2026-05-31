import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  notification,
} from "antd";
import {
  CheckOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  DownOutlined,
  FilterOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  TeamOutlined,
  UpOutlined,
} from "@ant-design/icons";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { getChatMembers, getChats } from "../api/chats";
import { getOrganizations } from "../api/organizations";
import {
  acceptResponse,
  addTaskAssignee,
  createTask,
  getInboxSummary,
  getTask,
  getTasks,
  rejectResponse,
  removeTaskAssignee,
  submitResponse,
  updateTask,
} from "../api/tasks";
import type { TaskListScope, TaskParticipantRole, TaskQuickStatus } from "../api/tasks";
import { getUsers } from "../api/users";
import { TaskStatusTag } from "../components/TaskStatusTag";
import { useAuth } from "../auth/useAuth";
import type { Chat } from "../types/chat";
import type { Organization } from "../types/organization";
import type {
  Task,
  TaskCompletionRule,
  TaskCreatePayload,
  TaskDetails,
  TaskInboxSummary,
  TaskPriority,
  TaskResponse,
  TaskStatus,
} from "../types/task";
import type { User } from "../types/user";
import { getChatDisplayTitle } from "../utils/chatDisplayTitle";
import { formatProjectDateTime } from "../utils/dateTime";

interface TaskFilters {
  chatId: string | null;
  dueToday: boolean;
  participantRole: TaskParticipantRole | null;
  participantUserId: string | null;
  quickStatus: TaskQuickStatus | null;
  search: string;
  scope: TaskListScope;
}

const defaultTaskFilters: TaskFilters = {
  chatId: null,
  dueToday: false,
  participantRole: null,
  participantUserId: null,
  quickStatus: null,
  search: "",
  scope: "all",
};

const priorityOptions: Array<{ label: string; value: TaskPriority }> = [
  { label: "Низкий", value: "low" },
  { label: "Обычный", value: "normal" },
  { label: "Высокий", value: "high" },
  { label: "Срочный", value: "urgent" },
];

const completionRuleOptions: Array<{ label: string; value: TaskCompletionRule }> = [
  { label: "Первый ответ исполнителя", value: "any_assignee_response" },
  { label: "Ответы всех исполнителей", value: "all_assignees_response" },
  { label: "Ручная отправка", value: "manual_submit" },
];
const futureDeadlineMessage = "Срок должен быть в будущем.";

const quickStatusOptions: Array<{ label: string; value: TaskQuickStatus }> = [
  { label: "Новые", value: "new" },
  { label: "Ждут отчета", value: "awaiting_report" },
  { label: "Ждут приемки", value: "awaiting_acceptance" },
  { label: "Просрочены", value: "overdue" },
];

const initialTaskSummary: TaskInboxSummary = {
  my_tasks: [],
  created_by_me: [],
  observed_by_me: [],
  new: [],
  waiting_my_response: [],
  waiting_my_acceptance: [],
  overdue: [],
  today: [],
  today_count: 0,
  new_count: 0,
  overdue_count: 0,
  awaiting_report_count: 0,
  awaiting_acceptance_count: 0,
};

interface TaskCreateFormValues {
  organization_id: string;
  chat_id: string;
  title: string;
  description?: string;
  created_by_user_id: string;
  deadline_at?: { toISOString: () => string } | null;
  priority: TaskPriority;
  completion_rule: TaskCompletionRule;
  assignee_ids?: string[];
  observer_ids?: string[];
}

interface TaskActionReportFormValues {
  text?: string;
}

interface TaskActionRejectFormValues {
  comment?: string;
}

interface TaskActionDeadlineFormValues {
  deadline_at?: { toISOString: () => string } | null;
}

interface TaskActionAssigneesFormValues {
  assignee_ids?: string[];
}

type TaskActionMode = "assignees" | "deadline" | "reject" | "report" | null;

export function TasksPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const [taskForm] = Form.useForm<TaskCreateFormValues>();
  const [actionReportForm] = Form.useForm<TaskActionReportFormValues>();
  const [actionRejectForm] = Form.useForm<TaskActionRejectFormValues>();
  const [actionDeadlineForm] = Form.useForm<TaskActionDeadlineFormValues>();
  const [actionAssigneesForm] = Form.useForm<TaskActionAssigneesFormValues>();
  const selectedOrganizationId = Form.useWatch("organization_id", taskForm);
  const [notificationApi, notificationContextHolder] = notification.useNotification();
  const initialFilters = useMemo(
    () => getInitialTaskFilters(location.search, location.hash),
    [location.hash, location.search],
  );
  const [filters, setFilters] = useState<TaskFilters>(() => initialFilters);
  const debouncedSearch = useDebouncedValue(filters.search.trim(), 350);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [summary, setSummary] = useState<TaskInboxSummary>(initialTaskSummary);
  const [users, setUsers] = useState<User[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [chatMemberUserIds, setChatMemberUserIds] = useState<Set<string> | null>(null);
  const [membersLoading, setMembersLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createOptionsLoading, setCreateOptionsLoading] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [showTestTasks, setShowTestTasks] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [selectedTaskDetails, setSelectedTaskDetails] = useState<TaskDetails | null>(null);
  const [taskSheetLoading, setTaskSheetLoading] = useState(false);
  const [taskActionMode, setTaskActionMode] = useState<TaskActionMode>(null);
  const [taskActionLoading, setTaskActionLoading] = useState<string | null>(null);
  const [taskSheetMemberUserIds, setTaskSheetMemberUserIds] = useState<Set<string> | null>(null);

  const loadTasks = useCallback(() => {
    setLoading(true);
    setError(null);

    getTasks({
      chat_id: filters.chatId ?? undefined,
      participant_role: filters.participantRole ?? undefined,
      participant_user_id: filters.participantUserId ?? undefined,
      due_today: filters.dueToday || undefined,
      quick_status: filters.quickStatus ?? undefined,
      scope: filters.scope,
      search: debouncedSearch,
      limit: 100,
    })
      .then(setTasks)
      .catch((requestError: unknown) => {
        setTasks([]);
        setError(requestError instanceof Error ? requestError.message : "Не удалось загрузить задачи");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [
    debouncedSearch,
    filters.chatId,
    filters.dueToday,
    filters.participantRole,
    filters.participantUserId,
    filters.quickStatus,
    filters.scope,
  ]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    let active = true;

    getInboxSummary({
      chat_id: filters.chatId ?? undefined,
    })
      .then((nextSummary) => {
        if (active) {
          setSummary(nextSummary);
        }
      })
      .catch(() => {
        if (active) {
          setSummary(initialTaskSummary);
        }
      });

    return () => {
      active = false;
    };
  }, [filters.chatId]);

  useEffect(() => {
    setFilters(initialFilters);
  }, [initialFilters]);

  useEffect(() => {
    Promise.allSettled([getUsers(), getChats()]).then(([usersResult, chatsResult]) => {
      setUsers(usersResult.status === "fulfilled" ? usersResult.value : []);
      setChats(chatsResult.status === "fulfilled" ? chatsResult.value : []);
    });
  }, []);

  useEffect(() => {
    if (!filters.chatId) {
      setChatMemberUserIds(null);
      setMembersLoading(false);
      return;
    }

    let active = true;
    setMembersLoading(true);
    getChatMembers(filters.chatId)
      .then((members) => {
        if (!active) {
          return;
        }
        setChatMemberUserIds(
          new Set(members.filter((member) => member.is_active).map((member) => member.user_id)),
        );
      })
      .catch(() => {
        if (active) {
          setChatMemberUserIds(new Set());
        }
      })
      .finally(() => {
        if (active) {
          setMembersLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [filters.chatId]);

  const filteredTasks = useMemo(() => {
    return showTestTasks ? tasks : tasks.filter((task) => !isDemoTask(task));
  }, [showTestTasks, tasks]);

  const hiddenTestTaskCount = useMemo(() => tasks.filter(isDemoTask).length, [tasks]);

  const taskKpis = useMemo(
    () => [
      { dueToday: true, label: "Сегодня", value: summary.today_count, tone: "default" as const },
      { label: "Новые", quickStatus: "new" as const, value: summary.new_count, tone: "default" as const },
      {
        label: "Ждут отчета",
        quickStatus: "awaiting_report" as const,
        value: summary.awaiting_report_count,
        tone: "info" as const,
      },
      {
        label: "Ждут приемки",
        quickStatus: "awaiting_acceptance" as const,
        value: summary.awaiting_acceptance_count,
        tone: "accent" as const,
      },
      {
        label: "Просрочены",
        quickStatus: "overdue" as const,
        value: summary.overdue_count,
        tone: "danger" as const,
      },
    ],
    [summary],
  );

  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const chatById = useMemo(() => new Map(chats.map((chat) => [chat.id, chat])), [chats]);
  const sheetTask = selectedTaskDetails ?? selectedTask;
  const selectedTaskStatus = sheetTask ? getTaskDisplayStatus(sheetTask) : null;
  const latestSubmittedResponse = selectedTaskDetails ? getLatestSubmittedResponse(selectedTaskDetails) : null;
  const isSheetTaskAssignee = Boolean(
    sheetTask && auth.userId && sheetTask.assignees.some((assignee) => assignee.user_id === auth.userId),
  );
  const isSheetTaskManager = Boolean(
    sheetTask &&
      auth.userId &&
      (sheetTask.created_by_user_id === auth.userId ||
        auth.roles.includes("super_admin") ||
        auth.roles.includes("chat_admin") ||
        auth.availableChats.some(
          (chat) =>
            chat.id === sheetTask.chat_id && (chat.role === "chat_admin" || chat.role === "super_admin"),
        )),
  );
  const canManageSheetTask = Boolean(sheetTask && isSheetTaskManager && !isFinalTaskStatus(sheetTask.status));
  const canSubmitSheetReport = Boolean(sheetTask && isSheetTaskAssignee && !isFinalTaskStatus(sheetTask.status));
  const canReviewSheetResponse = Boolean(
    selectedTaskDetails &&
      isSheetTaskManager &&
      selectedTaskDetails.status === "waiting_acceptance" &&
      latestSubmittedResponse,
  );
  const participantUsers = useMemo(() => {
    if (!filters.chatId || chatMemberUserIds === null) {
      return users;
    }
    return users.filter((user) => chatMemberUserIds.has(user.id));
  }, [chatMemberUserIds, filters.chatId, users]);

  const participantSelectValue = getParticipantSelectValue(filters);
  const hasActiveFilters = isAnyFilterActive(filters);
  const activeFilterCount = countActiveFilters(filters);

  const getUserLabel = useCallback(
    (userId: string) => {
      const user = userById.get(userId);
      return user?.display_name || "Пользователь";
    },
    [userById],
  );

  const updateFilter = <Key extends keyof TaskFilters>(key: Key, value: TaskFilters[Key]) => {
    setFilters((currentFilters) => ({
      ...currentFilters,
      [key]: value,
    }));
  };

  const updateChatFilter = (chatId: string | null) => {
    setFilters((currentFilters) => ({
      ...currentFilters,
      chatId,
      participantRole: null,
      participantUserId: null,
    }));
  };

  const updateParticipantFilter = (value: string) => {
    setFilters((currentFilters) => {
      if (value === "all") {
        return {
          ...currentFilters,
          participantRole: null,
          participantUserId: null,
          scope: "all",
        };
      }
      if (value === "me_assignee") {
        return {
          ...currentFilters,
          participantRole: null,
          participantUserId: null,
          scope: "assigned_to_me",
        };
      }
      if (value === "me_creator") {
        return {
          ...currentFilters,
          participantRole: null,
          participantUserId: null,
          scope: "created_by_me",
        };
      }

      const [role, userId] = value.split(":") as [TaskParticipantRole, string | undefined];
      return {
        ...currentFilters,
        participantRole: role,
        participantUserId: userId ?? null,
        scope: "all",
      };
    });
  };

  const toggleQuickStatus = (quickStatus: TaskQuickStatus) => {
    setFilters((currentFilters) => ({
      ...currentFilters,
      dueToday: false,
      quickStatus: currentFilters.quickStatus === quickStatus ? null : quickStatus,
    }));
  };

  const toggleDueToday = () => {
    setFilters((currentFilters) => ({
      ...currentFilters,
      dueToday: !currentFilters.dueToday,
      quickStatus: null,
    }));
  };

  const resetFilters = () => {
    setFilters(defaultTaskFilters);
  };

  const userOptions = useMemo(
    () =>
      users.map((user) => ({
        label: user.display_name || "Пользователь",
        value: user.id,
      })),
    [users],
  );

  const organizationOptions = useMemo(
    () =>
      organizations.map((organization) => ({
        label: organization.name,
        value: organization.id,
      })),
    [organizations],
  );

  const chatOptions = useMemo(
    () =>
      chats
        .filter((chat) => !selectedOrganizationId || chat.organization_id === selectedOrganizationId)
        .map((chat) => ({
          label: getChatDisplayTitle({ chat }),
          value: chat.id,
        })),
    [chats, selectedOrganizationId],
  );

  const taskChatOptions = useMemo(
    () =>
      chats.map((chat) => ({
        label: getChatDisplayTitle({ chat }),
        value: chat.id,
      })),
    [chats],
  );

  const participantOptions = useMemo(
    () => [
      {
        label: "Основные",
        options: [
          { label: "Все участники", value: "all" },
          { label: "Я исполнитель", value: "me_assignee" },
          { label: "Я постановщик", value: "me_creator" },
        ],
      },
      {
        label: "Исполнитель",
        options: participantUsers.map((user) => ({
          label: user.display_name,
          value: `assignee:${user.id}`,
        })),
      },
      {
        label: "Постановщик",
        options: participantUsers.map((user) => ({
          label: user.display_name,
          value: `creator:${user.id}`,
        })),
      },
    ],
    [participantUsers],
  );

  const sheetAssigneeOptions = useMemo(() => {
    const allowedUserIds = taskSheetMemberUserIds;
    return users
      .filter((user) => !allowedUserIds || allowedUserIds.has(user.id))
      .map((user) => ({
        label: user.display_name || "Пользователь",
        value: user.id,
      }));
  }, [taskSheetMemberUserIds, users]);

  const clearSearchFilter = () => {
    setFilters((currentFilters) => ({ ...currentFilters, search: "" }));
  };

  const clearDueTodayFilter = () => {
    setFilters((currentFilters) => ({ ...currentFilters, dueToday: false }));
  };

  const clearChatFilter = () => {
    setFilters((currentFilters) => ({
      ...currentFilters,
      chatId: null,
      participantRole: null,
      participantUserId: null,
    }));
  };

  const clearParticipantFilter = () => {
    setFilters((currentFilters) => ({
      ...currentFilters,
      participantRole: null,
      participantUserId: null,
      scope: "all",
    }));
  };

  const clearQuickStatusFilter = () => {
    setFilters((currentFilters) => ({ ...currentFilters, quickStatus: null }));
  };

  const activeFilterChips = useMemo(
    () =>
      buildActiveFilterChips({
        chatById,
        clearChatFilter,
        clearDueTodayFilter,
        clearParticipantFilter,
        clearQuickStatusFilter,
        clearSearchFilter,
        filters,
        userById,
      }),
    [chatById, filters, userById],
  );

  const openCreateModal = () => {
    taskForm.resetFields();
    taskForm.setFieldsValue({
      priority: "normal",
      completion_rule: "any_assignee_response",
      assignee_ids: [],
      observer_ids: [],
    });
    setCreateModalOpen(true);

    if (users.length > 0 && chats.length > 0 && organizations.length > 0) {
      return;
    }

    setCreateOptionsLoading(true);
    Promise.all([getUsers(), getChats(), getOrganizations()])
      .then(([nextUsers, nextChats, nextOrganizations]) => {
        setUsers(nextUsers);
        setChats(nextChats);
        setOrganizations(nextOrganizations);
      })
      .catch((requestError: unknown) => {
        notificationApi.error({
          message: "Не удалось загрузить данные для формы",
          description: requestError instanceof Error ? requestError.message : "Попробуйте открыть форму позже",
        });
      })
      .finally(() => {
        setCreateOptionsLoading(false);
      });
  };

  const closeCreateModal = () => {
    if (!createSubmitting) {
      setCreateModalOpen(false);
    }
  };

  const submitCreateTask = async () => {
    try {
      const values = await taskForm.validateFields();
      const payload: TaskCreatePayload = {
        organization_id: values.organization_id,
        chat_id: values.chat_id,
        title: values.title.trim(),
        description: values.description?.trim() || null,
        created_by_user_id: values.created_by_user_id,
        deadline_at: values.deadline_at?.toISOString() ?? null,
        priority: values.priority,
        completion_rule: values.completion_rule,
        assignee_ids: values.assignee_ids ?? [],
        observer_ids: values.observer_ids ?? [],
      };

      setCreateSubmitting(true);
      await createTask(payload);
      notificationApi.success({
        message: "Задача создана",
        description: payload.title,
      });
      setCreateModalOpen(false);
      taskForm.resetFields();
      loadTasks();
    } catch (requestError) {
      if (typeof requestError === "object" && requestError !== null && "errorFields" in requestError) {
        return;
      }

      notificationApi.error({
        message: "Не удалось создать задачу",
        description: friendlyTaskError(requestError),
      });
    } finally {
      setCreateSubmitting(false);
    }
  };

  const openTaskSheet = (task: Task) => {
    setSelectedTask(task);
    setSelectedTaskDetails(null);
    setTaskActionMode(null);
    setTaskSheetMemberUserIds(null);
    actionReportForm.resetFields();
    actionRejectForm.resetFields();
    actionDeadlineForm.resetFields();
    actionAssigneesForm.resetFields();
    setTaskSheetLoading(true);
    getTask(task.id)
      .then(setSelectedTaskDetails)
      .catch((requestError: unknown) => {
        notificationApi.warning({
          message: "Задача открыта в кратком режиме",
          description: friendlyTaskActionError(requestError),
        });
      })
      .finally(() => {
        setTaskSheetLoading(false);
      });
  };

  const closeTaskSheet = () => {
    if (taskActionLoading || taskActionMode) {
      return;
    }
    setSelectedTask(null);
    setSelectedTaskDetails(null);
    setTaskActionMode(null);
    setTaskSheetMemberUserIds(null);
  };

  const reloadSelectedTask = async () => {
    if (!sheetTask) {
      return;
    }
    const nextTask = await getTask(sheetTask.id);
    setSelectedTaskDetails(nextTask);
    setSelectedTask(nextTask);
    loadTasks();
  };

  const openFullTask = () => {
    if (!sheetTask) {
      return;
    }
    navigate(auth.withAuthSearch(`/tasks/${sheetTask.id}`));
  };

  const startReportAction = () => {
    actionReportForm.resetFields();
    setTaskActionMode("report");
  };

  const startRejectAction = () => {
    actionRejectForm.resetFields();
    setTaskActionMode("reject");
  };

  const startDeadlineAction = () => {
    actionDeadlineForm.resetFields();
    setTaskActionMode("deadline");
  };

  const startAssigneesAction = () => {
    if (!sheetTask) {
      return;
    }
    setTaskActionMode("assignees");
    actionAssigneesForm.setFieldsValue({
      assignee_ids: sheetTask.assignees.map((assignee) => assignee.user_id),
    });
    setTaskSheetMemberUserIds(null);
    getChatMembers(sheetTask.chat_id)
      .then((members) => {
        setTaskSheetMemberUserIds(new Set(members.filter((member) => member.is_active).map((member) => member.user_id)));
      })
      .catch(() => {
        notificationApi.warning({
          message: "Не удалось загрузить участников чата",
          description: "Показываем общий список пользователей.",
        });
      });
  };

  const closeTaskActionModal = () => {
    if (taskActionLoading) {
      return;
    }
    setTaskActionMode(null);
  };

  const submitSheetReport = async () => {
    if (!sheetTask || !auth.userId) {
      return;
    }
    let values: TaskActionReportFormValues;
    try {
      values = await actionReportForm.validateFields();
    } catch {
      return;
    }
    setTaskActionLoading("report");
    try {
      await submitResponse(sheetTask.id, {
        user_id: auth.userId,
        text: values.text?.trim() || null,
        source_message_id: null,
      });
      notificationApi.success({ message: "Отчет отправлен" });
      setTaskActionMode(null);
      actionReportForm.resetFields();
      await reloadSelectedTask();
    } catch (requestError) {
      notificationApi.error({
        message: "Не удалось отправить отчет",
        description: friendlyTaskActionError(requestError),
      });
    } finally {
      setTaskActionLoading(null);
    }
  };

  const acceptSheetResponse = async () => {
    if (!sheetTask || !latestSubmittedResponse || !auth.userId) {
      return;
    }
    setTaskActionLoading("accept");
    try {
      await acceptResponse(sheetTask.id, latestSubmittedResponse.id, {
        accepted_by_user_id: auth.userId,
        comment: null,
      });
      notificationApi.success({ message: "Ответ принят" });
      await reloadSelectedTask();
    } catch (requestError) {
      notificationApi.error({
        message: "Не удалось принять ответ",
        description: friendlyTaskActionError(requestError),
      });
    } finally {
      setTaskActionLoading(null);
    }
  };

  const confirmAcceptSheetResponse = () => {
    if (!sheetTask || !latestSubmittedResponse) {
      return;
    }
    Modal.confirm({
      title: "Принять отчет?",
      content: `Вы уверены, что хотите принять отчет по задаче ${sheetTask.task_ref}? После принятия задача будет завершена.`,
      okText: "Принять",
      cancelText: "Отмена",
      zIndex: 1300,
      onOk: () => acceptSheetResponse(),
    });
  };

  const submitSheetReject = async () => {
    if (!sheetTask || !latestSubmittedResponse || !auth.userId) {
      return;
    }
    let values: TaskActionRejectFormValues;
    try {
      values = await actionRejectForm.validateFields();
    } catch {
      return;
    }
    setTaskActionLoading("reject");
    try {
      await rejectResponse(sheetTask.id, latestSubmittedResponse.id, {
        accepted_by_user_id: auth.userId,
        comment: values.comment?.trim() || null,
      });
      notificationApi.success({ message: "Ответ отклонен" });
      setTaskActionMode(null);
      actionRejectForm.resetFields();
      await reloadSelectedTask();
    } catch (requestError) {
      notificationApi.error({
        message: "Не удалось отклонить ответ",
        description: friendlyTaskActionError(requestError),
      });
    } finally {
      setTaskActionLoading(null);
    }
  };

  const submitSheetDeadline = async () => {
    if (!sheetTask) {
      return;
    }
    let values: TaskActionDeadlineFormValues;
    try {
      values = await actionDeadlineForm.validateFields();
    } catch {
      return;
    }
    setTaskActionLoading("deadline");
    try {
      await updateTask(sheetTask.id, {
        deadline_at: values.deadline_at?.toISOString() ?? null,
      });
      notificationApi.success({ message: "Срок обновлен" });
      setTaskActionMode(null);
      actionDeadlineForm.resetFields();
      await reloadSelectedTask();
    } catch (requestError) {
      notificationApi.error({
        message: "Не удалось изменить срок",
        description: friendlyTaskActionError(requestError),
      });
    } finally {
      setTaskActionLoading(null);
    }
  };

  const submitSheetAssignees = async () => {
    if (!sheetTask) {
      return;
    }
    let values: TaskActionAssigneesFormValues;
    try {
      values = await actionAssigneesForm.validateFields();
    } catch {
      return;
    }
    const nextAssigneeIds = new Set(values.assignee_ids ?? []);
    const currentAssigneeIds = new Set(sheetTask.assignees.map((assignee) => assignee.user_id));
    const toAdd = [...nextAssigneeIds].filter((userId) => !currentAssigneeIds.has(userId));
    const toRemove = [...currentAssigneeIds].filter((userId) => !nextAssigneeIds.has(userId));

    setTaskActionLoading("assignees");
    try {
      await Promise.all([
        ...toAdd.map((userId) => addTaskAssignee(sheetTask.id, userId)),
        ...toRemove.map((userId) => removeTaskAssignee(sheetTask.id, userId)),
      ]);
      notificationApi.success({ message: "Исполнители обновлены" });
      setTaskActionMode(null);
      await reloadSelectedTask();
    } catch (requestError) {
      notificationApi.error({
        message: "Не удалось изменить исполнителей",
        description: friendlyTaskActionError(requestError),
      });
    } finally {
      setTaskActionLoading(null);
    }
  };

  return (
    <main className="page">
      {notificationContextHolder}
      <div className="page-heading tasks-page-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={2}>Дьяк</Typography.Title>
        </Space>
        <Space className="tasks-heading-actions" size={8}>
          <Tooltip title="Создать задачу">
            <Button
              aria-label="Создать задачу"
              className="tasks-heading-icon-button"
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreateModal}
            />
          </Tooltip>
          <Tooltip title="Обновить список">
            <Button
              aria-label="Обновить список"
              className="tasks-heading-icon-button"
              icon={<ReloadOutlined />}
              onClick={loadTasks}
            />
          </Tooltip>
        </Space>
      </div>

      <section className="tasks-kpi-scroll" aria-label="Сводные показатели задач">
        <div className="tasks-kpi-grid">
          {taskKpis.map((kpi) => (
            <KpiChip
              key={kpi.label}
              active={Boolean(
                (kpi.quickStatus && filters.quickStatus === kpi.quickStatus) ||
                  (kpi.dueToday && filters.dueToday),
              )}
              disabled={Boolean(
                kpi.value === 0 &&
                  !(
                    (kpi.quickStatus && filters.quickStatus === kpi.quickStatus) ||
                    (kpi.dueToday && filters.dueToday)
                  ),
              )}
              label={kpi.label}
              tone={kpi.tone}
              value={kpi.value}
              onToggle={
                kpi.dueToday
                  ? toggleDueToday
                  : kpi.quickStatus
                    ? () => toggleQuickStatus(kpi.quickStatus)
                    : undefined
              }
            />
          ))}
        </div>
      </section>

      {hiddenTestTaskCount > 0 ? (
        <div className="tasks-demo-filter">
          <InfoCircleOutlined className="tasks-demo-filter-icon" />
          <Space className="tasks-demo-filter-copy" direction="vertical" size={2}>
            <Typography.Text strong>Тестовые задачи скрыты</Typography.Text>
            <Typography.Text type="secondary">
              В списке скрыто тестовых задач: {hiddenTestTaskCount}. Данные не удаляются, это только фильтр
              интерфейса для демонстрации.
            </Typography.Text>
          </Space>
          <Checkbox checked={showTestTasks} onChange={(event) => setShowTestTasks(event.target.checked)}>
            Показать тестовые задачи
          </Checkbox>
        </div>
      ) : null}

      <section className="tasks-filter-spoiler" aria-label="Фильтры задач">
        <Button
          className="tasks-filter-toggle"
          icon={<FilterOutlined />}
          type={filtersExpanded ? "primary" : "default"}
          onClick={() => setFiltersExpanded((current) => !current)}
        >
          Фильтр{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}
          {filtersExpanded ? <UpOutlined /> : <DownOutlined />}
        </Button>

        {filtersExpanded ? (
          <div className="tasks-filter-panel">
            <Input.Search
              allowClear
              className="tasks-filter-search"
              enterButton={false}
              placeholder="#номер или текст задачи"
              value={filters.search}
              onChange={(event) => updateFilter("search", event.target.value)}
            />

            <div className="tasks-filter-control-row">
              <Select
                allowClear
                className="tasks-filter-select"
                notFoundContent="Вы пока не добавлены ни в один чат."
                optionFilterProp="label"
                options={taskChatOptions}
                placeholder="Все чаты"
                showSearch
                value={filters.chatId ?? undefined}
                onChange={(value) => updateChatFilter(value ?? null)}
              />
              <Select
                className="tasks-filter-select"
                loading={membersLoading}
                notFoundContent={filters.chatId ? "В чате нет участников." : "Участники не найдены."}
                optionFilterProp="label"
                options={participantOptions}
                placeholder="Участник"
                showSearch
                value={participantSelectValue}
                onChange={updateParticipantFilter}
              />
            </div>

            {activeFilterChips.length > 0 ? (
              <div className="tasks-active-filter-chips" aria-label="Активные фильтры">
                {activeFilterChips.map((chip) => (
                  <Tag key={chip.key} closable onClose={chip.onClose}>
                    {chip.label}
                  </Tag>
                ))}
              </div>
            ) : null}

            {hasActiveFilters ? (
              <Button className="tasks-reset-button" onClick={resetFilters}>
                Сбросить фильтры
              </Button>
            ) : null}
          </div>
        ) : null}
      </section>

      {error ? (
        <Alert
          className="tasks-alert"
          type="error"
          showIcon
          message="Не удалось загрузить задачи"
          description="Попробуйте обновить экран."
          action={
            <Button size="small" onClick={loadTasks}>
              Повторить
            </Button>
          }
        />
      ) : null}

      <div className="tasks-card-list-shell">
        <Spin spinning={loading} tip="Загружаем задачи…">
          {error ? null : filteredTasks.length > 0 ? (
            <div className="tasks-card-list">
              {filteredTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  assigneeText={formatAssigneeText(task, getUserLabel)}
                  creatorText={task.creator_display_name_snapshot || getUserLabel(task.created_by_user_id)}
                  chatText={getTaskChatDisplayTitle(task, chatById.get(task.chat_id))}
                  displayStatus={getTaskDisplayStatus(task)}
                  onOpen={() => openTaskSheet(task)}
                  onOpenFull={() => navigate(auth.withAuthSearch(`/tasks/${task.id}`))}
                />
              ))}
            </div>
          ) : (
            <TaskListEmptyState
              hasActiveFilters={hasActiveFilters}
              hasHiddenDemoTasks={hiddenTestTaskCount > 0 && !showTestTasks}
              summaryFilterActive={filters.dueToday || Boolean(filters.quickStatus)}
              onResetFilters={resetFilters}
              onShowDemoTasks={() => setShowTestTasks(true)}
            />
          )}
        </Spin>
      </div>

      <Modal
        title="Создать задачу"
        open={createModalOpen}
        okText="Создать"
        cancelText="Отмена"
        confirmLoading={createSubmitting}
        onCancel={closeCreateModal}
        onOk={submitCreateTask}
        width={760}
      >
        <Form<TaskCreateFormValues>
          form={taskForm}
          layout="vertical"
          className="task-create-form"
          initialValues={{
            priority: "normal",
            completion_rule: "any_assignee_response",
            assignee_ids: [],
            observer_ids: [],
          }}
        >
          <Form.Item
            label="Организация"
            name="organization_id"
            rules={[{ required: true, message: "Выберите организацию" }]}
          >
            <Select
              showSearch
              loading={createOptionsLoading}
              optionFilterProp="label"
              options={organizationOptions}
              placeholder="Выберите организацию"
              onChange={() => taskForm.setFieldValue("chat_id", undefined)}
            />
          </Form.Item>

          <Form.Item label="Чат" name="chat_id" rules={[{ required: true, message: "Выберите чат" }]}>
            <Select
              showSearch
              loading={createOptionsLoading}
              optionFilterProp="label"
              options={chatOptions}
              placeholder="Выберите чат"
            />
          </Form.Item>

          <Form.Item
            label="Название"
            name="title"
            rules={[{ required: true, whitespace: true, message: "Введите название задачи" }]}
          >
            <Input placeholder="Что нужно сделать" />
          </Form.Item>

          <Form.Item label="Описание" name="description">
            <Input.TextArea rows={3} placeholder="Контекст, детали, ожидаемый результат" />
          </Form.Item>

          <Form.Item
            label="Постановщик"
            name="created_by_user_id"
            rules={[{ required: true, message: "Выберите постановщика" }]}
          >
            <Select
              showSearch
              loading={createOptionsLoading}
              optionFilterProp="label"
              options={userOptions}
              placeholder="Выберите пользователя"
            />
          </Form.Item>

          <Space className="task-create-inline" size={12} align="start">
            <Form.Item label="Срок" name="deadline_at" rules={[{ validator: validateFutureDeadline }]}>
              <DatePicker
                showTime
                showNow
                format="DD.MM.YYYY HH:mm"
                popupClassName="mobile-safe-picker-dropdown"
                placement="bottomLeft"
                placeholder="Выберите дату и время"
              />
            </Form.Item>

            <Form.Item label="Приоритет" name="priority">
              <Select options={priorityOptions} />
            </Form.Item>

            <Form.Item label="Правило завершения" name="completion_rule">
              <Select options={completionRuleOptions} />
            </Form.Item>
          </Space>

          <Form.Item label="Исполнители" name="assignee_ids">
            <Select
              mode="multiple"
              allowClear
              showSearch
              loading={createOptionsLoading}
              optionFilterProp="label"
              options={userOptions}
              placeholder="Выберите одного или нескольких исполнителей"
            />
          </Form.Item>

          <Form.Item label="Наблюдатели" name="observer_ids">
            <Select
              mode="multiple"
              allowClear
              showSearch
              loading={createOptionsLoading}
              optionFilterProp="label"
              options={userOptions}
              placeholder="Выберите наблюдателей"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        className="task-action-sheet"
        destroyOnClose
        height="80vh"
        open={Boolean(sheetTask)}
        placement="bottom"
        title={sheetTask ? `${sheetTask.task_ref} · действия` : "Действия"}
        onClose={closeTaskSheet}
      >
        {sheetTask ? (
          <Spin spinning={taskSheetLoading}>
            <div className="task-action-sheet-body">
              <div className="task-action-summary">
                <Space size={8} wrap>
                  <Typography.Text className="task-card-ref" strong>
                    {sheetTask.task_ref}
                  </Typography.Text>
                  {selectedTaskStatus ? <TaskStatusTag status={selectedTaskStatus} /> : null}
                </Space>
                <Typography.Title className="task-action-title" level={4}>
                  {sanitizeUserFacingText(sheetTask.title) || sheetTask.task_ref}
                </Typography.Title>
                <div className="task-action-meta">
                  <TaskMetaRow label="Срок" value={formatDeadline(sheetTask.deadline_at, selectedTaskStatus ?? sheetTask.status)} />
                  <TaskMetaRow label={formatAssigneeText(sheetTask, getUserLabel).label} value={formatAssigneeText(sheetTask, getUserLabel).value} />
                  <TaskMetaRow label="Постановщик" value={sheetTask.creator_display_name_snapshot || getUserLabel(sheetTask.created_by_user_id)} />
                  <TaskMetaRow label="Отчет" value={formatReportSummary(selectedTaskDetails, getUserLabel)} />
                </div>
              </div>

              <div className="task-action-buttons">
                {canSubmitSheetReport ? (
                  <Button icon={<SendOutlined />} onClick={startReportAction}>
                    Написать отчет
                  </Button>
                ) : null}
                {canReviewSheetResponse ? (
                  <>
                    <Button
                      icon={<CheckOutlined />}
                      loading={taskActionLoading === "accept"}
                      onClick={confirmAcceptSheetResponse}
                    >
                      Принять
                    </Button>
                    <Button icon={<CloseOutlined />} onClick={startRejectAction}>
                      Отклонить
                    </Button>
                  </>
                ) : null}
                {canManageSheetTask ? (
                  <>
                    <Button icon={<ClockCircleOutlined />} onClick={startDeadlineAction}>
                      Изменить срок
                    </Button>
                    <Button icon={<TeamOutlined />} onClick={startAssigneesAction}>
                      Изменить исполнителей
                    </Button>
                  </>
                ) : null}
                <Button icon={<FileTextOutlined />} type="primary" onClick={openFullTask}>
                  Открыть полностью
                </Button>
              </div>
            </div>
          </Spin>
        ) : null}
      </Drawer>

      <Modal
        className="task-action-modal"
        destroyOnClose
        title={sheetTask ? `Отчет по задаче ${sheetTask.task_ref}` : "Отчет по задаче"}
        open={taskActionMode === "report"}
        okText="Отправить отчет"
        cancelText="Отмена"
        confirmLoading={taskActionLoading === "report"}
        zIndex={1200}
        onCancel={closeTaskActionModal}
        onOk={() => void submitSheetReport()}
      >
        <Form<TaskActionReportFormValues> form={actionReportForm} layout="vertical">
          <Form.Item
            label="Текст отчета"
            name="text"
            rules={[{ required: true, whitespace: true, message: "Напишите отчет" }]}
          >
            <Input.TextArea rows={5} placeholder="Что сделано, ссылки, комментарии" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        className="task-action-modal"
        destroyOnClose
        title={sheetTask ? `Отклонить отчет по задаче ${sheetTask.task_ref}` : "Отклонить отчет"}
        open={taskActionMode === "reject"}
        okText="Отклонить отчет"
        cancelText="Отмена"
        confirmLoading={taskActionLoading === "reject"}
        zIndex={1200}
        onCancel={closeTaskActionModal}
        onOk={() => void submitSheetReject()}
      >
        <Form<TaskActionRejectFormValues> form={actionRejectForm} layout="vertical">
          <Form.Item
            label="Причина отклонения"
            name="comment"
            rules={[{ required: true, whitespace: true, message: "Укажите причину" }]}
          >
            <Input.TextArea rows={5} placeholder="Что нужно исправить" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        className="task-action-modal"
        destroyOnClose
        title={sheetTask ? `Изменить срок задачи ${sheetTask.task_ref}` : "Изменить срок задачи"}
        open={taskActionMode === "deadline"}
        okText="Сохранить срок"
        cancelText="Отмена"
        confirmLoading={taskActionLoading === "deadline"}
        zIndex={1200}
        onCancel={closeTaskActionModal}
        onOk={() => void submitSheetDeadline()}
      >
        <Form<TaskActionDeadlineFormValues> form={actionDeadlineForm} layout="vertical">
          <Form.Item
            label="Новый срок"
            name="deadline_at"
            rules={[
              { required: true, message: "Укажите новый срок" },
              { validator: validateFutureDeadline },
            ]}
          >
            <DatePicker
              className="task-action-modal-picker"
              popupClassName="mobile-safe-picker-dropdown task-action-picker-dropdown"
              showTime
              showNow
              format="DD.MM.YYYY HH:mm"
              getPopupContainer={getTaskActionPopupContainer}
              placement="bottomLeft"
              placeholder="Выберите дату и время"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        className="task-action-modal"
        destroyOnClose
        title={sheetTask ? `Изменить исполнителей задачи ${sheetTask.task_ref}` : "Изменить исполнителей"}
        open={taskActionMode === "assignees"}
        okText="Сохранить"
        cancelText="Отмена"
        confirmLoading={taskActionLoading === "assignees"}
        zIndex={1200}
        onCancel={closeTaskActionModal}
        onOk={() => void submitSheetAssignees()}
      >
        <Form<TaskActionAssigneesFormValues> form={actionAssigneesForm} layout="vertical">
          <Form.Item
            label="Исполнители"
            name="assignee_ids"
            rules={[
              {
                validator: (_rule, value: string[] | undefined) =>
                  value && value.length > 0
                    ? Promise.resolve()
                    : Promise.reject(new Error("Выберите хотя бы одного исполнителя")),
              },
            ]}
          >
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              options={sheetAssigneeOptions}
              placeholder="Выберите исполнителей"
            />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}

interface AssigneeDisplay {
  label: "Исполнитель" | "Исполнители";
  value: string;
}

interface ActiveFilterChip {
  key: string;
  label: string;
  onClose: () => void;
}

function buildActiveFilterChips({
  chatById,
  clearChatFilter,
  clearDueTodayFilter,
  clearParticipantFilter,
  clearQuickStatusFilter,
  clearSearchFilter,
  filters,
  userById,
}: {
  chatById: Map<string, Chat>;
  clearChatFilter: () => void;
  clearDueTodayFilter: () => void;
  clearParticipantFilter: () => void;
  clearQuickStatusFilter: () => void;
  clearSearchFilter: () => void;
  filters: TaskFilters;
  userById: Map<string, User>;
}): ActiveFilterChip[] {
  const chips: ActiveFilterChip[] = [];

  if (filters.search.trim()) {
    chips.push({
      key: "search",
      label: `Поиск: ${filters.search.trim()}`,
      onClose: clearSearchFilter,
    });
  }

  if (filters.dueToday) {
    chips.push({
      key: "due_today",
      label: "Сегодня",
      onClose: clearDueTodayFilter,
    });
  }

  if (filters.chatId) {
    const chat = chatById.get(filters.chatId);
    chips.push({
      key: "chat",
      label: `Чат: ${chat ? getChatDisplayTitle({ chat }) : "выбранный чат"}`,
      onClose: clearChatFilter,
    });
  }

  const participantLabel = getParticipantFilterLabel(filters, userById);
  if (participantLabel) {
    chips.push({
      key: "participant",
      label: participantLabel,
      onClose: clearParticipantFilter,
    });
  }

  if (filters.quickStatus) {
    chips.push({
      key: "quick_status",
      label: getQuickStatusLabel(filters.quickStatus),
      onClose: clearQuickStatusFilter,
    });
  }

  return chips;
}

function KpiChip({
  active = false,
  disabled = false,
  label,
  onToggle,
  tone = "default",
  value,
}: {
  active?: boolean;
  disabled?: boolean;
  label: string;
  onToggle?: () => void;
  tone?: "accent" | "danger" | "default" | "info";
  value: number;
}) {
  const className = [
    "tasks-kpi-card",
    `tasks-kpi-card-${tone}`,
    active ? "tasks-kpi-card-active" : "",
    disabled ? "tasks-kpi-card-disabled" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Card
      className={className}
      role={onToggle && !disabled ? "button" : undefined}
      size="small"
      tabIndex={onToggle && !disabled ? 0 : undefined}
      onClick={disabled ? undefined : onToggle}
      onKeyDown={(event) => {
        if (!onToggle || disabled) {
          return;
        }
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      }}
    >
      <Typography.Text className="tasks-kpi-label" type="secondary">
        {label}
      </Typography.Text>
      <Typography.Text className="tasks-kpi-value" strong>
        {value}
      </Typography.Text>
    </Card>
  );
}

function TaskCard({
  assigneeText,
  chatText,
  creatorText,
  displayStatus,
  onOpen,
  onOpenFull,
  task,
}: {
  assigneeText: AssigneeDisplay;
  chatText: string;
  creatorText: string;
  displayStatus: TaskStatus;
  onOpen: () => void;
  onOpenFull: () => void;
  task: Task;
}) {
  return (
    <Card
      className="task-card"
      role="button"
      size="small"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="task-card-header">
        <Space size={8} wrap>
          <Typography.Text className="task-card-ref" strong>
            {task.task_ref}
          </Typography.Text>
          <TaskStatusTag status={displayStatus} />
        </Space>
        <Button
          type="link"
          size="small"
          onClick={(event) => {
            event.stopPropagation();
            onOpenFull();
          }}
        >
          Открыть
        </Button>
      </div>

      <Typography.Title className="task-card-title" level={4}>
        {sanitizeUserFacingText(task.title) || task.task_ref}
      </Typography.Title>

      <div className="task-card-meta">
        <TaskMetaRow label={assigneeText.label} value={assigneeText.value} />
        <TaskMetaRow label="Постановщик" value={creatorText} />
        <TaskMetaRow label="Срок" value={formatDeadline(task.deadline_at, displayStatus)} />
        <TaskMetaRow label="Чат" value={chatText} />
      </div>
    </Card>
  );
}

function TaskMetaRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="task-card-meta-row">
      <Typography.Text className="task-card-meta-label" type="secondary">
        {label}
      </Typography.Text>
      <Typography.Text className="task-card-meta-value">{value}</Typography.Text>
    </div>
  );
}

function TaskListEmptyState({
  hasActiveFilters,
  hasHiddenDemoTasks,
  summaryFilterActive,
  onResetFilters,
  onShowDemoTasks,
}: {
  hasActiveFilters: boolean;
  hasHiddenDemoTasks: boolean;
  summaryFilterActive: boolean;
  onResetFilters: () => void;
  onShowDemoTasks: () => void;
}) {
  return (
    <Empty
      className="tasks-empty-state"
      description={
        <Space direction="vertical" size={4}>
          <Typography.Text>
            {hasActiveFilters
              ? summaryFilterActive
                ? "По этому фильтру задач нет."
                : "По этим фильтрам задач нет."
              : "Задач пока нет."}
          </Typography.Text>
          <Typography.Text type="secondary">
            {hasActiveFilters
              ? "Попробуйте изменить поиск, чат, участника или статус."
              : hasHiddenDemoTasks
                ? "Все найденные задачи сейчас скрыты demo-фильтром."
                : "Создайте задачу в MAX командой /задача."}
          </Typography.Text>
        </Space>
      }
    >
      <Space wrap>
        {hasActiveFilters ? <Button onClick={onResetFilters}>Сбросить фильтры</Button> : null}
        {hasHiddenDemoTasks ? <Button onClick={onShowDemoTasks}>Показать тестовые задачи</Button> : null}
      </Space>
    </Empty>
  );
}

function formatAssigneeText(task: Task, getUserLabel: (userId: string) => string): AssigneeDisplay {
  const names = task.assignees.map((assignee) => getUserLabel(assignee.user_id));
  return {
    label: names.length === 1 ? "Исполнитель" : "Исполнители",
    value: names.length > 0 ? names.join(", ") : "не назначены",
  };
}

function formatDate(value: string | null, emptyText = "Нет данных") {
  if (!value) {
    return <Tag>{emptyText}</Tag>;
  }

  return formatProjectDateTime(value);
}

function formatDeadline(value: string | null, status: TaskStatus) {
  if (!value) {
    return <Tag>Без срока</Tag>;
  }

  const text = formatDate(value);
  if (status !== "overdue") {
    return text;
  }

  return (
    <Tag className="tasks-deadline-overdue" color="default">
      {text}
    </Tag>
  );
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

function getTaskActionPopupContainer(trigger: HTMLElement): HTMLElement {
  const modal = trigger.closest(".task-action-modal");
  return modal instanceof HTMLElement ? modal : document.body;
}

function friendlyTaskError(error: unknown): string {
  if (error instanceof ApiError && error.details && typeof error.details === "object") {
    const detail = (error.details as { detail?: unknown }).detail;
    if (detail === "deadline_must_be_in_future") {
      return futureDeadlineMessage;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Проверьте данные и повторите попытку";
}

function friendlyTaskActionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Недостаточно прав для действия.";
    }
    if (error.status === 404) {
      return "Задача изменилась. Обновите список.";
    }
    if (error.details && typeof error.details === "object") {
      const detail = (error.details as { detail?: unknown }).detail;
      if (detail === "deadline_must_be_in_future") {
        return futureDeadlineMessage;
      }
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Не удалось выполнить действие. Попробуйте еще раз.";
}

function getTaskDisplayStatus(task: Task): TaskStatus {
  if (isTaskOverdue(task)) {
    return "overdue";
  }
  return task.status;
}

function isTaskOverdue(task: Task): boolean {
  if (!task.deadline_at || isFinalTaskStatus(task.status)) {
    return false;
  }
  return new Date(task.deadline_at).getTime() < Date.now();
}

function isFinalTaskStatus(status: TaskStatus): boolean {
  return status === "done" || status === "cancelled" || status === "rejected";
}

function getTaskChatDisplayTitle(task: Task, chat: Chat | undefined): string {
  return getChatDisplayTitle({
    chat,
    sourceTitle: task.source_chat_title_snapshot,
  });
}

function getLatestSubmittedResponse(task: TaskDetails): TaskResponse | null {
  return [...task.responses]
    .filter((response) => response.status === "submitted")
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0] ?? null;
}

function getLatestResponse(task: TaskDetails): TaskResponse | null {
  return [...task.responses].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  )[0] ?? null;
}

function getResponseStatusLabel(status: TaskResponse["status"]): string {
  const labels: Record<TaskResponse["status"], string> = {
    accepted: "принят",
    rejected: "отклонен",
    submitted: "ожидает приемки",
  };
  return labels[status];
}

function formatReportSummary(
  task: TaskDetails | null,
  getUserLabel: (userId: string) => string,
): string {
  if (!task) {
    return "загружаем";
  }
  const response = getLatestResponse(task);
  if (!response) {
    return "отчетов пока нет";
  }
  const authorName = getUserLabel(response.user_id);
  return `${getResponseStatusLabel(response.status)} · ${authorName} · ${formatProjectDateTime(response.created_at)}`;
}

function sanitizeUserFacingText(value: string): string {
  return value
    .split("\n")
    .filter((line) => !isTechnicalMetadataLine(line))
    .join("\n")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, "")
    .replace(new RegExp("\\bpayload=" + "task:[^\\s]+", "gi"), "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isTechnicalMetadataLine(line: string): boolean {
  return (
    /^\s*(payload|callback[_\s-]?payload)\s*[:=]/i.test(line) ||
    /^\s*(task|chat|user|max[_\s-]?(chat|user))[_\s-]?id\s*[:=]/i.test(line) ||
    /^\s*(uuid|group)\s*#?\s*[:=]/i.test(line) ||
    /^\s*(пользователь|группа)\s*#\d+/i.test(line)
  );
}

function isDemoTask(task: Task): boolean {
  return /^(smoke|webapp smoke)\b/i.test(task.title.trim());
}

function getParticipantSelectValue(filters: TaskFilters): string {
  if (filters.scope === "assigned_to_me") {
    return "me_assignee";
  }
  if (filters.scope === "created_by_me") {
    return "me_creator";
  }
  if (filters.participantRole && filters.participantUserId) {
    return `${filters.participantRole}:${filters.participantUserId}`;
  }
  return "all";
}

function getParticipantFilterLabel(filters: TaskFilters, userById: Map<string, User>): string | null {
  if (filters.scope === "assigned_to_me") {
    return "Я исполнитель";
  }
  if (filters.scope === "created_by_me") {
    return "Я постановщик";
  }
  if (!filters.participantRole || !filters.participantUserId) {
    return null;
  }

  const userName = userById.get(filters.participantUserId)?.display_name ?? "выбранный пользователь";
  return filters.participantRole === "assignee"
    ? `Исполнитель: ${userName}`
    : `Постановщик: ${userName}`;
}

function getQuickStatusLabel(quickStatus: TaskQuickStatus): string {
  return quickStatusOptions.find((option) => option.value === quickStatus)?.label ?? quickStatus;
}

function isAnyFilterActive(filters: TaskFilters): boolean {
  return (
    Boolean(filters.search.trim()) ||
    filters.dueToday ||
    Boolean(filters.chatId) ||
    Boolean(filters.participantRole && filters.participantUserId) ||
    filters.scope !== "all" ||
    Boolean(filters.quickStatus)
  );
}

function countActiveFilters(filters: TaskFilters): number {
  return [
    Boolean(filters.search.trim()),
    filters.dueToday,
    Boolean(filters.chatId),
    Boolean(filters.participantRole && filters.participantUserId) || filters.scope !== "all",
    Boolean(filters.quickStatus),
  ].filter(Boolean).length;
}

function getInitialTaskFilters(search: string, hash: string): TaskFilters {
  const startApp = getStartAppValue(search, hash);
  const taskNumber = startApp?.match(/^task_(\d+)$/i)?.[1];
  return {
    ...defaultTaskFilters,
    search: taskNumber ? `#${taskNumber}` : "",
    scope: startApp === "my_tasks" ? "assigned_to_me" : "all",
  };
}

function getStartAppValue(search: string, hash: string): string | null {
  return (
    getUrlValue(search, "startapp") ??
    getUrlValue(search, "startApp") ??
    getUrlValue(search, "start_param") ??
    getUrlValue(hash, "startapp") ??
    getUrlValue(hash, "startApp") ??
    getUrlValue(hash, "start_param")
  );
}

function getUrlValue(source: string, key: string): string | null {
  const normalized = source.replace(/^[?#]/, "");
  const queryString = normalized.includes("?") ? normalized.slice(normalized.indexOf("?") + 1) : normalized;
  const params = new URLSearchParams(queryString);
  return params.get(key);
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      setDebouncedValue(value);
    }, delayMs);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [delayMs, value]);

  return debouncedValue;
}
