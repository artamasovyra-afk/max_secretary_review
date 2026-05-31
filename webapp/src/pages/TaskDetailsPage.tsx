import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
  notification,
} from "antd";
import {
  ArrowLeftOutlined,
  CheckOutlined,
  CloseOutlined,
  CommentOutlined,
  FileAddOutlined,
  SendOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { getChats } from "../api/chats";
import {
  acceptResponse,
  addComment,
  addFile,
  cancelTask,
  getTask,
  rejectResponse,
  submitResponse,
} from "../api/tasks";
import { getUsers } from "../api/users";
import { useAuth } from "../auth/useAuth";
import { BitrixSyncStatusCard } from "../components/BitrixSyncStatusCard";
import { CompletionRuleTag } from "../components/CompletionRuleTag";
import { TaskPriorityTag } from "../components/TaskPriorityTag";
import { TaskStatusTag } from "../components/TaskStatusTag";
import type { TaskDetails, TaskFileCreatePayload, TaskResponse, TaskStatus } from "../types/task";
import type { Chat } from "../types/chat";
import type { User } from "../types/user";
import { getChatDisplayTitle } from "../utils/chatDisplayTitle";
import { formatProjectDateTime } from "../utils/dateTime";

interface CommentFormValues {
  text: string;
}

interface FileFormValues {
  file_name: string;
  file_url?: string;
  mime_type?: string;
  size_bytes?: number | null;
}

interface ResponseFormValues {
  text?: string;
}

interface RejectFormValues {
  comment?: string;
}

export function TaskDetailsPage() {
  const { taskId } = useParams();
  const navigate = useNavigate();
  const auth = useAuth();
  const userId = auth.userId ?? "";
  const [notificationApi, notificationContextHolder] = notification.useNotification();
  const [modalApi, modalContextHolder] = Modal.useModal();
  const [commentForm] = Form.useForm<CommentFormValues>();
  const [fileForm] = Form.useForm<FileFormValues>();
  const [responseForm] = Form.useForm<ResponseFormValues>();
  const [rejectForm] = Form.useForm<RejectFormValues>();

  const [task, setTask] = useState<TaskDetails | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [commentModalOpen, setCommentModalOpen] = useState(false);
  const [fileModalOpen, setFileModalOpen] = useState(false);
  const [responseModalOpen, setResponseModalOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<TaskResponse | null>(null);

  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const chatById = useMemo(() => new Map(chats.map((chat) => [chat.id, chat])), [chats]);
  const taskChatTitle = task ? getTaskChatDisplayTitle(task, chatById.get(task.chat_id)) : "Чат без названия";
  const taskTitle = task ? sanitizeUserFacingText(task.title) || task.task_ref : "Карточка задачи";
  const taskDescription = task?.description ? sanitizeTaskDescription(task.description) : "";
  const taskDisplayStatus = task ? getTaskDisplayStatus(task) : null;

  const getUserLabel = useCallback(
    (nextUserId: string | null | undefined) => {
      if (!nextUserId) {
        return "Не указан";
      }

      const user = userById.get(nextUserId);
      return user?.display_name || "Пользователь";
    },
    [userById],
  );

  const loadTask = useCallback(() => {
    if (!taskId) {
      setError("Не указан идентификатор задачи");
      return;
    }

    setLoading(true);
    setError(null);

    getTask(taskId)
      .then(setTask)
      .catch((requestError: unknown) => {
        setTask(null);
        setError(requestError instanceof Error ? requestError.message : "Не удалось загрузить задачу");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [taskId]);

  useEffect(() => {
    loadTask();
  }, [loadTask]);

  useEffect(() => {
    Promise.allSettled([getUsers(), getChats()]).then(([usersResult, chatsResult]) => {
      setUsers(usersResult.status === "fulfilled" ? usersResult.value : []);
      setChats(chatsResult.status === "fulfilled" ? chatsResult.value : []);
    });
  }, []);

  const goBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate(auth.withAuthSearch("/tasks"));
  };

  const runAction = async (key: string, action: () => Promise<void>, successMessage: string) => {
    setActionLoading(key);
    try {
      await action();
      notificationApi.success({ message: successMessage });
      loadTask();
    } catch (requestError) {
      notificationApi.error({
        message: "Действие не выполнено",
        description: requestError instanceof Error ? requestError.message : "Проверьте данные и повторите попытку",
      });
    } finally {
      setActionLoading(null);
    }
  };

  const openCommentModal = () => {
    commentForm.resetFields();
    setCommentModalOpen(true);
  };

  const openFileModal = () => {
    fileForm.resetFields();
    setFileModalOpen(true);
  };

  const openResponseModal = () => {
    responseForm.resetFields();
    setResponseModalOpen(true);
  };

  const submitComment = async () => {
    if (!taskId || !userId) {
      return;
    }

    const values = await commentForm.validateFields();
    await runAction(
      "comment",
      async () => {
        await addComment(taskId, {
          user_id: userId,
          text: values.text.trim(),
          reply_to_comment_id: null,
        });
        setCommentModalOpen(false);
      },
      "Комментарий добавлен",
    );
  };

  const submitFileMetadata = async () => {
    if (!taskId || !userId) {
      return;
    }

    const values = await fileForm.validateFields();
    const payload: TaskFileCreatePayload = {
      uploaded_by_user_id: userId,
      comment_id: null,
      file_name: values.file_name.trim(),
      file_url: values.file_url?.trim() || null,
      file_storage_key: null,
      mime_type: values.mime_type?.trim() || null,
      size_bytes: values.size_bytes ?? null,
    };

    await runAction(
      "file",
      async () => {
        await addFile(taskId, payload);
        setFileModalOpen(false);
      },
      "Файл добавлен как metadata",
    );
  };

  const submitTaskResponse = async () => {
    if (!taskId || !userId) {
      return;
    }

    const values = await responseForm.validateFields();
    await runAction(
      "response",
      async () => {
        await submitResponse(taskId, {
          user_id: userId,
          text: values.text?.trim() || null,
          source_message_id: null,
        });
        setResponseModalOpen(false);
      },
      "Ответ отправлен",
    );
  };

  const acceptTaskResponse = (response: TaskResponse) => {
    if (!taskId || !userId) {
      return;
    }

    modalApi.confirm({
      title: "Принять ответ?",
      content: "Задача будет переведена в статус done.",
      okText: "Принять",
      cancelText: "Отмена",
      onOk: () =>
        runAction(
          `accept-${response.id}`,
          async () => {
            await acceptResponse(taskId, response.id, {
              accepted_by_user_id: userId,
              comment: null,
            });
          },
          "Ответ принят",
        ),
    });
  };

  const openRejectModal = (response: TaskResponse) => {
    rejectForm.resetFields();
    setRejectTarget(response);
  };

  const submitRejectResponse = async () => {
    if (!taskId || !userId || !rejectTarget) {
      return;
    }

    const values = await rejectForm.validateFields();
    await runAction(
      `reject-${rejectTarget.id}`,
      async () => {
        await rejectResponse(taskId, rejectTarget.id, {
          accepted_by_user_id: userId,
          comment: values.comment?.trim() || null,
        });
        setRejectTarget(null);
      },
      "Ответ отклонен",
    );
  };

  const confirmCancelTask = () => {
    if (!taskId) {
      return;
    }

    modalApi.confirm({
      title: "Отменить задачу?",
      content: "Отмена изменит статус задачи на cancelled.",
      okText: "Отменить задачу",
      cancelText: "Назад",
      onOk: () =>
        runAction(
          "cancel",
          async () => {
            await cancelTask(taskId);
          },
          "Задача отменена",
        ),
    });
  };

  return (
    <main className="page">
      {notificationContextHolder}
      {modalContextHolder}

      <div className="page-heading">
        <Space direction="vertical" size={4}>
          <Button className="task-details-back-button" icon={<ArrowLeftOutlined />} onClick={goBack}>
            Назад
          </Button>
          <Typography.Title level={2}>{taskTitle}</Typography.Title>
          {task ? (
            <Space size={[8, 8]} wrap>
              <Typography.Text strong>{task.task_ref}</Typography.Text>
              {taskDisplayStatus ? <TaskStatusTag status={taskDisplayStatus} /> : null}
            </Space>
          ) : null}
        </Space>
      </div>

      {!userId ? (
        <Alert
          className="tasks-alert"
          type="warning"
          showIcon
          message="Пользователь сессии не определен"
          description="Откройте WebApp из MAX или обновите страницу, чтобы восстановить доступ к действиям."
        />
      ) : null}

      {loading ? (
        <div className="dashboard-state">
          <Spin tip="Загрузка карточки задачи" />
        </div>
      ) : null}

      {error ? (
        <Alert type="error" showIcon message="Не удалось загрузить задачу" description={error} />
      ) : null}

      {!loading && !error && task ? (
        <Space className="task-details-stack" direction="vertical" size={16}>
          <Card title="Основное">
            <Descriptions column={{ xs: 1, sm: 1, md: 2 }} bordered size="small">
              <Descriptions.Item label="Срок">{formatDeadline(task.deadline_at, taskDisplayStatus ?? task.status)}</Descriptions.Item>
              <Descriptions.Item label="Постановщик">{getUserLabel(task.created_by_user_id)}</Descriptions.Item>
              <Descriptions.Item label="Исполнители" span={2}>
                {renderUserTags(task.assignees.map((assignee) => assignee.user_id), getUserLabel)}
              </Descriptions.Item>
              <Descriptions.Item label="Наблюдатели" span={2}>
                {renderUserTags(task.observers.map((observer) => observer.user_id), getUserLabel)}
              </Descriptions.Item>
              <Descriptions.Item label="Чат">{taskChatTitle}</Descriptions.Item>
              <Descriptions.Item label="Приоритет">
                <TaskPriorityTag priority={task.priority} />
              </Descriptions.Item>
              <Descriptions.Item label="Правило завершения">
                <CompletionRuleTag completionRule={task.completion_rule} />
              </Descriptions.Item>
              <Descriptions.Item label="Создана">{formatDate(task.created_at)}</Descriptions.Item>
              <Descriptions.Item label="Обновлена">{formatDate(task.updated_at)}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="Описание">
            <Typography.Paragraph className="task-details-description">
              {taskDescription || "Описание не указано."}
            </Typography.Paragraph>
          </Card>

          <Card
            title="Комментарии"
            extra={
              userId ? (
                <Button icon={<CommentOutlined />} onClick={openCommentModal}>
                  Добавить комментарий
                </Button>
              ) : null
            }
          >
            <List
              dataSource={task.comments}
              locale={{ emptyText: <Empty description="Комментариев пока нет" /> }}
              renderItem={(comment) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <span>{getUserLabel(comment.user_id)}</span>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        <Typography.Text>{sanitizeUserFacingText(comment.text) || "Без текста"}</Typography.Text>
                        <Typography.Text type="secondary">{formatDate(comment.created_at)}</Typography.Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>

          <Card
            title="Файлы"
            extra={
              userId ? (
                <Button icon={<FileAddOutlined />} onClick={openFileModal}>
                  Добавить metadata файла
                </Button>
              ) : null
            }
          >
            <List
              dataSource={task.files}
              locale={{ emptyText: <Empty description="Файлы пока не добавлены" /> }}
              renderItem={(file) => (
                <List.Item>
                  <List.Item.Meta
                    title={file.file_name}
                    description={
                      <Space direction="vertical" size={4}>
                        <Space size={[4, 4]} wrap>
                          <Tag>{file.mime_type || "mime не указан"}</Tag>
                          <Tag>{file.size_bytes === null ? "размер не указан" : `${file.size_bytes} bytes`}</Tag>
                          <Tag>Добавил: {getUserLabel(file.uploaded_by_user_id)}</Tag>
                        </Space>
                        {file.file_url ? <Typography.Text copyable>{file.file_url}</Typography.Text> : null}
                        <Typography.Text type="secondary">{formatDate(file.created_at)}</Typography.Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>

          <Card
            title="Ответы исполнителей"
            extra={
              userId ? (
                <Button icon={<SendOutlined />} onClick={openResponseModal}>
                  Отправить ответ
                </Button>
              ) : null
            }
          >
            <List
              dataSource={task.responses}
              locale={{ emptyText: <Empty description="Ответов пока нет" /> }}
              renderItem={(response) => (
                <List.Item
                  actions={
                    userId
                      ? [
                          <Button
                            key="accept"
                            size="small"
                            type="link"
                            icon={<CheckOutlined />}
                            loading={actionLoading === `accept-${response.id}`}
                            onClick={() => acceptTaskResponse(response)}
                          >
                            Принять
                          </Button>,
                          <Button
                            key="reject"
                            size="small"
                            type="link"
                            icon={<CloseOutlined />}
                            loading={actionLoading === `reject-${response.id}`}
                            onClick={() => openRejectModal(response)}
                          >
                            Отклонить
                          </Button>,
                        ]
                      : undefined
                  }
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <span>{getUserLabel(response.user_id)}</span>
                        <Tag color={response.status === "accepted" ? "green" : response.status === "rejected" ? "default" : "gold"}>
                          {getResponseStatusLabel(response.status)}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        <Typography.Text>{response.text ? sanitizeUserFacingText(response.text) || "Без текста" : "Без текста"}</Typography.Text>
                        <Typography.Text type="secondary">{formatDate(response.created_at)}</Typography.Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>

          <Card title="История статусов">
            {task.status_history.length > 0 ? (
              <Timeline
                items={task.status_history.map((history) => ({
                  children: (
                    <Space direction="vertical" size={2}>
                      <Typography.Text>
                        {history.old_status ? getTaskStatusLabel(history.old_status) : "Создана"} →{" "}
                        {getTaskStatusLabel(history.new_status)}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        {formatDate(history.created_at)} · {getUserLabel(history.changed_by_user_id)}
                      </Typography.Text>
                    </Space>
                  ),
                }))}
              />
            ) : (
              <Empty description="История статусов пуста" />
            )}
          </Card>

          <Card title="Управление" className="task-details-danger-card">
            <Space direction="vertical" size={8}>
              <Typography.Text type="secondary">
                Отмена задачи доступна только пользователям с нужными правами. Это действие изменит статус задачи.
              </Typography.Text>
              <Button danger icon={<StopOutlined />} disabled={!task || !userId} onClick={confirmCancelTask}>
                Отменить задачу
              </Button>
            </Space>
          </Card>

          <BitrixSyncStatusCard taskId={task.id} />
        </Space>
      ) : null}

      <Modal
        title="Добавить комментарий"
        open={commentModalOpen}
        okText="Добавить"
        cancelText="Отмена"
        confirmLoading={actionLoading === "comment"}
        onCancel={() => setCommentModalOpen(false)}
        onOk={submitComment}
      >
        <Form<CommentFormValues> form={commentForm} layout="vertical">
          <Form.Item name="text" label="Комментарий" rules={[{ required: true, whitespace: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Добавить metadata файла"
        open={fileModalOpen}
        okText="Добавить"
        cancelText="Отмена"
        confirmLoading={actionLoading === "file"}
        onCancel={() => setFileModalOpen(false)}
        onOk={submitFileMetadata}
      >
        <Form<FileFormValues> form={fileForm} layout="vertical">
          <Form.Item name="file_name" label="Имя файла" rules={[{ required: true, whitespace: true }]}>
            <Input placeholder="report.pdf" />
          </Form.Item>
          <Form.Item name="file_url" label="URL файла">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="mime_type" label="MIME type">
            <Input placeholder="application/pdf" />
          </Form.Item>
          <Form.Item name="size_bytes" label="Размер, bytes">
            <InputNumber min={0} precision={0} className="task-details-number-input" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Отправить ответ исполнителя"
        open={responseModalOpen}
        okText="Отправить"
        cancelText="Отмена"
        confirmLoading={actionLoading === "response"}
        onCancel={() => setResponseModalOpen(false)}
        onOk={submitTaskResponse}
      >
        <Form<ResponseFormValues> form={responseForm} layout="vertical">
          <Form.Item name="text" label="Ответ">
            <Input.TextArea rows={4} placeholder="Что сделано, ссылки, комментарии" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Отклонить ответ"
        open={Boolean(rejectTarget)}
        okText="Отклонить"
        cancelText="Отмена"
        confirmLoading={Boolean(rejectTarget && actionLoading === `reject-${rejectTarget.id}`)}
        onCancel={() => setRejectTarget(null)}
        onOk={submitRejectResponse}
      >
        <Form<RejectFormValues> form={rejectForm} layout="vertical">
          <Form.Item name="comment" label="Комментарий">
            <Input.TextArea rows={4} placeholder="Что нужно исправить" />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
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

function renderUserTags(userIds: string[], getUserLabel: (userId: string) => string) {
  if (userIds.length === 0) {
    return <Tag>Нет</Tag>;
  }

  return (
    <Space size={[0, 4]} wrap>
      {userIds.map((userId) => (
        <Tag key={userId}>{getUserLabel(userId)}</Tag>
      ))}
    </Space>
  );
}

function getTaskChatDisplayTitle(task: TaskDetails, chat: Chat | undefined): string {
  return getChatDisplayTitle({
    chat,
    sourceTitle: task.source_chat_title_snapshot,
  });
}

function sanitizeTaskDescription(value: string): string {
  return value
    .split("\n")
    .map((line) => sanitizeUserFacingText(line))
    .filter((line) => line.trim().length > 0)
    .filter((line) => !isTechnicalMetadataLine(line))
    .join("\n")
    .trim();
}

function sanitizeUserFacingText(value: string): string {
  return value
    .split("\n")
    .map((line) =>
      line.replace(
        /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi,
        "",
      ),
    )
    .map((line) => line.replace(/\bmid[.:_-]?[A-Za-z0-9_-]{8,}\b/g, ""))
    .filter((line) => !/^\s*(id|uuid|task[_\s-]?id|source[_\s-]?message[_\s-]?id|command[_\s-]?message[_\s-]?id)\s*[:=]?\s*$/i.test(line))
    .join("\n")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isTechnicalMetadataLine(line: string): boolean {
  return (
    /^\s*(исходное сообщение max|автор исходного сообщения max|команда max)\s*[:=]/i.test(line) ||
    /^\s*(source|command|reply)?[_\s-]?(message[_\s-]?id|mid|uuid|task[_\s-]?id|chat[_\s-]?id|user[_\s-]?id|max[_\s-]?(chat|user)[_\s-]?id)\s*[:=]/i.test(line) ||
    /\b(source|command|reply).*\b(message[_\s-]?id|mid)\b/i.test(line)
  );
}

function getTaskStatusLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    new: "Новая",
    in_progress: "В работе",
    waiting_response: "Ждет отчета",
    waiting_acceptance: "Ждет приемки",
    done: "Выполнена",
    overdue: "Просрочена",
    rejected: "Отклонена",
    cancelled: "Отменена",
  };
  return labels[status];
}

function getTaskDisplayStatus(task: TaskDetails): TaskStatus {
  if (isTaskOverdue(task)) {
    return "overdue";
  }
  return task.status;
}

function isTaskOverdue(task: TaskDetails): boolean {
  if (!task.deadline_at || isFinalTaskStatus(task.status)) {
    return false;
  }
  return new Date(task.deadline_at).getTime() < Date.now();
}

function isFinalTaskStatus(status: TaskStatus): boolean {
  return status === "done" || status === "cancelled" || status === "rejected";
}

function getResponseStatusLabel(status: TaskResponse["status"]): string {
  const labels: Record<TaskResponse["status"], string> = {
    submitted: "Отправлен",
    accepted: "Принят",
    rejected: "Отклонен",
  };
  return labels[status];
}
