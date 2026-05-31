import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Space, Spin, Tag, Typography } from "antd";
import { getBitrixTaskSyncStatus, syncBitrixTask } from "../api/bitrix24";
import { ApiError } from "../api/client";
import type { BitrixSyncStatus, BitrixTaskSyncStatusResponse } from "../types/bitrix24";

const statusColor: Record<BitrixSyncStatus, string> = {
  disabled: "default",
  pending: "gold",
  synced: "green",
  error: "orange",
};

const statusLabel: Record<BitrixSyncStatus, string> = {
  disabled: "Интеграция выключена",
  pending: "Не синхронизировано",
  synced: "Синхронизировано",
  error: "Ошибка синхронизации",
};

interface BitrixSyncStatusCardProps {
  taskId: string;
}

export function BitrixSyncStatusCard({ taskId }: BitrixSyncStatusCardProps) {
  const [status, setStatus] = useState<BitrixTaskSyncStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const authUnavailable = isAuthRequiredMessage(error) || isAuthRequiredMessage(syncError);

  const loadStatus = useCallback(() => {
    setLoading(true);
    setError(null);

    getBitrixTaskSyncStatus(taskId)
      .then(setStatus)
      .catch((requestError: unknown) => {
        setStatus(null);
        setError(getErrorMessage(requestError));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [taskId]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const runSync = async () => {
    setSyncing(true);
    setSyncError(null);

    try {
      const nextStatus = await syncBitrixTask(taskId);
      setStatus(nextStatus);
    } catch (requestError) {
      setSyncError(getErrorMessage(requestError));
      loadStatus();
    } finally {
      setSyncing(false);
    }
  };

  return (
    <Card
      title="Битрикс24"
      extra={
        <Space wrap>
          {status?.sync_status === "error" ? (
            <Button loading={syncing} onClick={runSync}>
              Повторить синхронизацию
            </Button>
          ) : null}
          <Button
            type="primary"
            disabled={authUnavailable}
            loading={syncing}
            title={authUnavailable ? "Требуется авторизация" : undefined}
            onClick={runSync}
          >
            Синхронизировать с Битрикс24
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={12} className="task-details-stack">
        {loading ? <Spin tip="Загрузка статуса синхронизации" /> : null}

        {error ? (
          <Alert
            type={authUnavailable ? "info" : "warning"}
            showIcon
            message={
              authUnavailable
                ? "Статус Битрикс24 недоступен в текущем режиме доступа"
                : "Не удалось загрузить статус синхронизации"
            }
            description={error}
          />
        ) : null}

        {syncError ? (
          <Alert
            type={isAuthRequiredMessage(syncError) ? "info" : "warning"}
            showIcon
            message={
              isAuthRequiredMessage(syncError)
                ? "Синхронизация требует авторизации"
                : "Синхронизация не выполнена"
            }
            description={syncError}
          />
        ) : null}

        {!loading && !error && !status ? (
          <Alert type="info" showIcon message="Статус синхронизации пока недоступен" />
        ) : null}

        {status ? (
          <Space direction="vertical" size={8}>
            <Space size={[8, 8]} wrap>
              <Typography.Text type="secondary">Статус:</Typography.Text>
              <Tag color={statusColor[status.sync_status]}>{statusLabel[status.sync_status]}</Tag>
            </Space>

            {status.sync_status === "disabled" ? (
              <Alert
                type="info"
                showIcon
                message="Интеграция Битрикс24 выключена"
                description="Это нормальное состояние для окружения без реального webhook."
              />
            ) : null}

            {status.bitrix_task_id ? (
              <Typography.Text>
                ID задачи в Битрикс24: <Typography.Text code>{status.bitrix_task_id}</Typography.Text>
              </Typography.Text>
            ) : null}

            {status.last_sync_at ? (
              <Typography.Text type="secondary">
                Последняя синхронизация: {formatDate(status.last_sync_at)}
              </Typography.Text>
            ) : null}

            {status.last_error ? (
              <Alert
                type="warning"
                showIcon
                message="Последняя ошибка"
                description={sanitizeLastError(status.last_error)}
              />
            ) : null}
          </Space>
        ) : null}
      </Space>
    </Card>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Для просмотра статуса синхронизации требуется авторизация.";
  }
  if (error instanceof Error && /header auth is disabled/i.test(error.message)) {
    return "Для просмотра статуса синхронизации требуется авторизация.";
  }
  return error instanceof Error ? error.message : "Проверьте соединение и повторите попытку";
}

function isAuthRequiredMessage(value: string | null): boolean {
  return Boolean(value && /требуется авторизация/i.test(value));
}

function sanitizeLastError(value: string): string {
  return value
    .replace(/https?:\/\/\S+/gi, "[url скрыт]")
    .replace(/webhook\/[^\s/]+(?:\/[^\s/]+)?/gi, "webhook/[секрет скрыт]");
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}
