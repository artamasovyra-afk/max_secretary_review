export type TaskStatus =
  | "new"
  | "in_progress"
  | "waiting_response"
  | "waiting_acceptance"
  | "done"
  | "overdue"
  | "rejected"
  | "cancelled";

export type TaskPriority = "low" | "normal" | "high" | "urgent";

export type TaskType = "personal" | "group_assignment";

export type TaskCompletionRule =
  | "any_assignee_response"
  | "all_assignees_response"
  | "manual_submit";

export interface TaskAssignee {
  id: string;
  task_id: string;
  user_id: string;
  status: "assigned" | "in_progress" | "responded" | "rejected" | "completed";
  response_required: boolean;
  responded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskObserver {
  id: string;
  task_id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface TaskComment {
  id: string;
  task_id: string;
  user_id: string;
  text: string;
  reply_to_comment_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskFile {
  id: string;
  task_id: string;
  comment_id: string | null;
  uploaded_by_user_id: string;
  file_name: string;
  file_url: string | null;
  file_storage_key: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  created_at: string;
}

export interface TaskResponse {
  id: string;
  task_id: string;
  user_id: string;
  text: string | null;
  source_message_id: string | null;
  status: "submitted" | "accepted" | "rejected";
  created_at: string;
  updated_at: string;
}

export interface TaskStatusHistory {
  id: string;
  task_id: string;
  old_status: TaskStatus | null;
  new_status: TaskStatus;
  changed_by_user_id: string | null;
  created_at: string;
}

export interface Task {
  id: string;
  organization_id: string;
  chat_id: string;
  task_number: number;
  task_ref: string;
  task_type: TaskType;
  requires_individual_report: boolean;
  audience_snapshot: Record<string, unknown> | null;
  title: string;
  description: string | null;
  created_by_user_id: string;
  creator_display_name_snapshot: string | null;
  creator_role_snapshot: string | null;
  source_chat_title_snapshot: string | null;
  deadline_at: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  completion_rule: TaskCompletionRule;
  submitted_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  assignees: TaskAssignee[];
  observers: TaskObserver[];
}

export interface TaskDetails extends Task {
  comments: TaskComment[];
  files: TaskFile[];
  responses: TaskResponse[];
  status_history: TaskStatusHistory[];
}

export interface TaskCreatePayload {
  organization_id: string;
  chat_id: string;
  title: string;
  description?: string | null;
  created_by_user_id: string;
  deadline_at?: string | null;
  priority?: TaskPriority;
  completion_rule?: TaskCompletionRule;
  assignee_ids?: string[];
  observer_ids?: string[];
}

export interface TaskGroupAssignmentCreatePayload {
  organization_id: string;
  chat_id: string;
  created_by_user_id: string;
  title: string;
  description?: string | null;
  deadline_at?: string | null;
  assignee_ids?: string[];
  exclude_creator?: boolean;
  response_required?: boolean;
}

export interface TaskGroupAssignmentCreateResponse {
  task_id: string;
  task_number: number;
  task_ref: string;
  total_assignees: number;
  creator_display_name: string | null;
  creator_role: string | null;
}

export interface TaskGroupReportUser {
  user_id: string;
  display_name: string;
}

export interface TaskGroupReportCreator {
  user_id: string;
  display_name: string;
  role: string | null;
}

export interface TaskGroupReportChat {
  chat_id: string;
  title: string;
}

export interface TaskGroupReportItem {
  user: TaskGroupReportUser;
  status: TaskAssignee["status"];
  responded_at: string | null;
  response_text: string | null;
}

export interface TaskGroupReport {
  task_id: string;
  task_number: number;
  task_ref: string;
  title: string;
  creator: TaskGroupReportCreator;
  chat: TaskGroupReportChat;
  total: number;
  responded: number;
  pending: number;
  overdue: number;
  items: TaskGroupReportItem[];
}

export interface TaskUpdatePayload {
  title?: string;
  description?: string | null;
  deadline_at?: string | null;
  priority?: TaskPriority;
  completion_rule?: TaskCompletionRule;
  status?: TaskStatus;
}

export interface TaskCommentCreatePayload {
  user_id: string;
  text: string;
  reply_to_comment_id?: string | null;
}

export interface TaskFileCreatePayload {
  uploaded_by_user_id: string;
  comment_id?: string | null;
  file_name: string;
  file_url?: string | null;
  file_storage_key?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
}

export interface TaskResponseCreatePayload {
  user_id: string;
  text?: string | null;
  source_message_id?: string | null;
}

export interface TaskAcceptancePayload {
  accepted_by_user_id: string;
  comment?: string | null;
}

export interface TaskAcceptance {
  id: string;
  task_id: string;
  response_id: string;
  accepted_by_user_id: string;
  decision: "accepted" | "rejected";
  comment: string | null;
  created_at: string;
}

export interface TaskInboxSummary {
  my_tasks: Task[];
  created_by_me: Task[];
  observed_by_me: Task[];
  new: Task[];
  waiting_my_response: Task[];
  waiting_my_acceptance: Task[];
  overdue: Task[];
  today: Task[];
  today_count: number;
  new_count: number;
  overdue_count: number;
  awaiting_report_count: number;
  awaiting_acceptance_count: number;
}
