import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Descriptions, Empty, Space, Spin, Statistic, Table, Tag, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { getChats } from "../api/chats";
import { ApiError } from "../api/client";
import { getGroupAssignmentReport, getTask } from "../api/tasks";
import { useAuth } from "../auth/useAuth";
import { TaskStatusTag } from "../components/TaskStatusTag";
import type { Chat } from "../types/chat";
import type { TaskDetails, TaskGroupReport, TaskGroupReportItem } from "../types/task";
import { getChatDisplayTitle } from "../utils/chatDisplayTitle";

export function GroupAssignmentDetailsPage() {
  const { taskId } = useParams();
  const navigate = useNavigate();
  const auth = useAuth();
  const [report, setReport] = useState<TaskGroupReport | null>(null);
  const [task, setTask] = useState<TaskDetails | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatById = useMemo(() => new Map(chats.map((chat) => [chat.id, chat])), [chats]);

  const loadReport = useCallback(() => {
    if (!taskId) {
      setError("Не указан идентификатор задачи");
      return;
    }

    setLoading(true);
    setError(null);
    Promise.all([getGroupAssignmentReport(taskId), getTask(taskId), getChats()])
      .then(([nextReport, nextTask, nextChats]) => {
        setReport(nextReport);
        setTask(nextTask);
        setChats(nextChats);
      })
      .catch((requestError: unknown) => {
        setReport(null);
        setTask(null);
        setError(friendlyReportError(requestError));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [taskId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const columns = useMemo<TableColumnsType<TaskGroupReportItem>>(
    () => [
      {
        title: "Участник",
        key: "user",
        width: 220,
        render: (_, item) => (
          <Typography.Text ellipsis={{ tooltip: userLabel(item.user) }}>{userLabel(item.user)}</Typography.Text>
        ),
      },
      {
        title: "Статус",
        dataIndex: "status",
        key: "status",
        width: 150,
        render: (status: TaskGroupReportItem["status"]) => assigneeStatusTag(status),
      },
      {
        title: "Ответ",
        dataIndex: "response_text",
        key: "response_text",
        render: (text: string | null) =>
          text ? (
            <Typography.Paragraph className="group-report-response" ellipsis={{ rows: 2, tooltip: text }}>
              {text}
            </Typography.Paragraph>
          ) : (
            <Typography.Text type="secondary">Ответа пока нет</Typography.Text>
          ),
      },
      {
        title: "Время ответа",
        dataIndex: "responded_at",
        key: "responded_at",
        width: 170,
        render: (value: string | null) => formatDate(value, "Нет ответа"),
      },
    ],
    [],
  );

  return (
    <main className="page">
      <div className="page-heading tasks-page-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={2}>{report?.title ?? "Задача участникам чата"}</Typography.Title>
          {report ? <Typography.Text type="secondary">{report.task_ref}</Typography.Text> : null}
        </Space>
        <Space wrap>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(auth.withAuthSearch("/group-assignments"))}>
            К списку
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadReport}>
            Обновить
          </Button>
        </Space>
      </div>

      {loading ? (
        <div className="dashboard-state">
          <Spin tip="Загрузка отчета" />
        </div>
      ) : null}

      {error ? (
        <Alert
          className="tasks-alert"
          type={error.includes("режиме доступа") ? "info" : "error"}
          showIcon
          message="Не удалось загрузить отчет по задаче участникам чата"
          description={error}
        />
      ) : null}

      {!loading && !error && report ? (
        <Space className="task-details-stack" direction="vertical" size={16}>
          <Card className="settings-card">
            <Descriptions column={{ xs: 1, md: 2 }} size="small">
              <Descriptions.Item label="Постановщик">
                {report.creator.display_name || `Пользователь #${shortTail(report.creator.user_id)}`}
              </Descriptions.Item>
              <Descriptions.Item label="Роль постановщика">{roleLabel(report.creator.role)}</Descriptions.Item>
              <Descriptions.Item label="Чат">
                {getChatDisplayTitle({
                  chat: chatById.get(report.chat.chat_id),
                  sourceTitle: task?.source_chat_title_snapshot ?? report.chat.title,
                })}
              </Descriptions.Item>
              <Descriptions.Item label="Срок">{formatDate(task?.deadline_at ?? null, "Без срока")}</Descriptions.Item>
              <Descriptions.Item label="Статус">
                {task ? <TaskStatusTag status={task.status} /> : <Tag>Нет данных</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="Обязательный отчет">
                {task?.requires_individual_report ? <Tag color="blue">Да</Tag> : <Tag>Нет</Tag>}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <section className="tasks-kpi-grid" aria-label="Сводные показатели отчета">
            <Card className="tasks-kpi-card" size="small">
              <Statistic title="Всего" value={report.total} />
            </Card>
            <Card className="tasks-kpi-card" size="small">
              <Statistic title="Выполнили" value={report.responded} valueStyle={{ color: "#16a34a" }} />
            </Card>
            <Card className="tasks-kpi-card" size="small">
              <Statistic title="Ожидают" value={report.pending} valueStyle={{ color: "#2563eb" }} />
            </Card>
            <Card className="tasks-kpi-card" size="small">
              <Statistic title="Просрочено" value={report.overdue} valueStyle={{ color: "#dc2626" }} />
            </Card>
          </section>

          <Card className="settings-card" title="Индивидуальные отчеты">
            <div className="tasks-table-shell">
              <Table<TaskGroupReportItem>
                rowKey={(item) => item.user.user_id}
                columns={columns}
                dataSource={report.items}
                pagination={false}
                scroll={{ x: 860 }}
                size="small"
                locale={{
                  emptyText: <Empty description="По этой задаче пока нет данных отчета." />,
                }}
              />
            </div>
          </Card>
        </Space>
      ) : null}
    </main>
  );
}

function userLabel(user: TaskGroupReportItem["user"]): string {
  return user.display_name || `Пользователь #${shortTail(user.user_id)}`;
}

function assigneeStatusTag(status: TaskGroupReportItem["status"]) {
  const labels: Record<TaskGroupReportItem["status"], { label: string; color?: string }> = {
    assigned: { label: "Ожидает", color: "blue" },
    in_progress: { label: "В работе", color: "processing" },
    responded: { label: "Ответил", color: "green" },
    rejected: { label: "Отклонен", color: "default" },
    completed: { label: "Выполнено", color: "success" },
  };
  const item = labels[status] ?? { label: status };
  return <Tag color={item.color}>{item.label}</Tag>;
}

function roleLabel(role: string | null): string {
  const labels: Record<string, string> = {
    chat_admin: "Админ чата",
    member: "Участник",
    super_admin: "Суперадмин",
  };
  return role ? labels[role] ?? role : "Роль не указана";
}

function formatDate(value: string | null, emptyText: string) {
  if (!value) {
    return <Tag>{emptyText}</Tag>;
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

function friendlyReportError(error: unknown): string {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return "Отчет недоступен для текущего пользователя или роли.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Проверьте доступ и повторите попытку";
}

function shortTail(value: string) {
  return value.length > 4 ? value.slice(-4) : value;
}
