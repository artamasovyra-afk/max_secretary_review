import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, Empty, Space, Spin, Table, Tag, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { getInboxSummary } from "../api/tasks";
import { useAuth } from "../auth/useAuth";
import { TaskStatusTag } from "../components/TaskStatusTag";
import type { Task, TaskInboxSummary } from "../types/task";

interface DashboardBlock {
  key: keyof TaskInboxSummary;
  title: string;
  tasks: Task[];
}

export function DashboardPage() {
  const navigate = useNavigate();
  const auth = useAuth();
  const userId = auth.userId ?? "";
  const [summary, setSummary] = useState<TaskInboxSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) {
      setSummary(null);
      setError(null);
      setLoading(false);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    getInboxSummary()
      .then((data) => {
        if (isMounted) {
          setSummary(data);
        }
      })
      .catch((requestError: unknown) => {
        if (isMounted) {
          setSummary(null);
          setError(requestError instanceof Error ? requestError.message : "Не удалось загрузить свод задач");
        }
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [userId]);

  const columns = useMemo<TableColumnsType<Task>>(
    () => [
      {
        title: "Название",
        dataIndex: "title",
        key: "title",
        render: (title: string, task) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong ellipsis={{ tooltip: title }}>
              {title}
            </Typography.Text>
            <Typography.Text type="secondary">{task.task_ref}</Typography.Text>
          </Space>
        ),
      },
      {
        title: "Статус",
        dataIndex: "status",
        key: "status",
        width: 170,
        render: (status: Task["status"]) => <TaskStatusTag status={status} />,
      },
      {
        title: "Срок",
        dataIndex: "deadline_at",
        key: "deadline_at",
        width: 170,
        render: (deadlineAt: string | null) => formatDeadline(deadlineAt),
      },
      {
        title: "Чат",
        dataIndex: "chat_id",
        key: "chat_id",
        width: 160,
        render: (chatId: string) => <Tag>{shortId(chatId)}</Tag>,
      },
      {
        title: "",
        key: "open",
        width: 150,
        align: "right",
        render: (_, task) => (
          <Button type="link" size="small" onClick={() => navigate(auth.withAuthSearch(`/tasks/${task.id}`))}>
            Открыть карточку
          </Button>
        ),
      },
    ],
    [auth, navigate],
  );

  const blocks = useMemo<DashboardBlock[]>(
    () => [
      {
        key: "my_tasks",
        title: "Мои задачи",
        tasks: summary?.my_tasks ?? [],
      },
      {
        key: "created_by_me",
        title: "Поставленные мной",
        tasks: summary?.created_by_me ?? [],
      },
      {
        key: "observed_by_me",
        title: "Наблюдаемые",
        tasks: summary?.observed_by_me ?? [],
      },
      {
        key: "waiting_my_response",
        title: "Ожидают моего ответа",
        tasks: summary?.waiting_my_response ?? [],
      },
      {
        key: "waiting_my_acceptance",
        title: "Ожидают моей приемки",
        tasks: summary?.waiting_my_acceptance ?? [],
      },
      {
        key: "overdue",
        title: "Просроченные",
        tasks: summary?.overdue ?? [],
      },
      {
        key: "today",
        title: "На сегодня",
        tasks: summary?.today ?? [],
      },
    ],
    [summary],
  );

  return (
    <main className="page">
      <div className="page-heading">
        <Space direction="vertical" size={4}>
          <Typography.Title level={2}>Единый свод задач</Typography.Title>
          {auth.user ? (
            <Typography.Text type="secondary">Пользователь: {auth.user.display_name}</Typography.Text>
          ) : null}
        </Space>
      </div>

      {!userId ? (
        <Card className="dashboard-card">
          <Space className="dashboard-empty-cta" direction="vertical" size={16}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <Space direction="vertical" size={4}>
                  <Typography.Text strong>Пользователь сессии не определен</Typography.Text>
                  <Typography.Text type="secondary">
                    Откройте WebApp из MAX или обновите страницу, чтобы восстановить сессию.
                  </Typography.Text>
                </Space>
              }
            />
            <Button onClick={() => navigate("/tasks")}>Перейти к задачам</Button>
          </Space>
        </Card>
      ) : null}

      {userId && loading ? (
        <div className="dashboard-state">
          <Spin tip="Загрузка свода задач" />
        </div>
      ) : null}

      {userId && error ? (
        <Alert
          type="error"
          showIcon
          message="Не удалось загрузить свод задач"
          description={error}
        />
      ) : null}

      {userId && !loading && !error && summary ? (
        <section className="dashboard-grid">
          {blocks.map((block) => (
            <Card
              key={block.key}
              className="dashboard-card"
              title={
                <Space size={8}>
                  <span>{block.title}</span>
                  <Tag color="blue">{block.tasks.length}</Tag>
                </Space>
              }
            >
              {block.tasks.length > 0 ? (
                <Table
                  columns={columns}
                  dataSource={block.tasks}
                  pagination={false}
                  rowKey="id"
                  scroll={{ x: 760 }}
                  size="small"
                />
              ) : (
                <Empty description="Нет задач" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          ))}
        </section>
      ) : null}
    </main>
  );
}

function formatDeadline(deadlineAt: string | null) {
  if (!deadlineAt) {
    return <Tag>Без срока</Tag>;
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(deadlineAt));
}

function shortId(value: string) {
  return value.length > 12 ? value.slice(0, 8) : value;
}
