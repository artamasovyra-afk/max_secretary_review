import { Tag } from "antd";
import type { TaskPriority } from "../types/task";

const priorityColor: Record<TaskPriority, string> = {
  low: "default",
  normal: "default",
  high: "orange",
  urgent: "orange",
};

const priorityLabel: Record<TaskPriority, string> = {
  low: "Низкий",
  normal: "Обычный",
  high: "Высокий",
  urgent: "Срочный",
};

interface TaskPriorityTagProps {
  priority: TaskPriority;
}

export function TaskPriorityTag({ priority }: TaskPriorityTagProps) {
  return <Tag color={priorityColor[priority]}>{priorityLabel[priority]}</Tag>;
}
