import { Tag } from "antd";
import type { TaskStatus } from "../types/task";

const statusColor: Record<TaskStatus, string> = {
  new: "default",
  in_progress: "processing",
  waiting_response: "gold",
  waiting_acceptance: "purple",
  done: "green",
  overdue: "red",
  rejected: "default",
  cancelled: "default",
};

const statusLabel: Record<TaskStatus, string> = {
  new: "Новая",
  in_progress: "В работе",
  waiting_response: "Ждет отчета",
  waiting_acceptance: "Ждет приемки",
  done: "Выполнена",
  overdue: "Просрочена",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

interface TaskStatusTagProps {
  status: TaskStatus;
}

export function TaskStatusTag({ status }: TaskStatusTagProps) {
  return <Tag color={statusColor[status]}>{statusLabel[status]}</Tag>;
}
