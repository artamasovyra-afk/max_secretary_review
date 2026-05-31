import { Tag } from "antd";
import type { TaskCompletionRule } from "../types/task";

const completionRuleColor: Record<TaskCompletionRule, string> = {
  any_assignee_response: "blue",
  all_assignees_response: "purple",
  manual_submit: "default",
};

const completionRuleLabel: Record<TaskCompletionRule, string> = {
  any_assignee_response: "Первый ответ",
  all_assignees_response: "Ответы всех",
  manual_submit: "Ручная отправка",
};

interface CompletionRuleTagProps {
  completionRule: TaskCompletionRule;
}

export function CompletionRuleTag({ completionRule }: CompletionRuleTagProps) {
  return <Tag color={completionRuleColor[completionRule]}>{completionRuleLabel[completionRule]}</Tag>;
}
