import { request } from "./client";
import type {
  Task,
  TaskAcceptance,
  TaskAcceptancePayload,
  TaskAssignee,
  TaskComment,
  TaskCommentCreatePayload,
  TaskDetails,
  TaskFile,
  TaskFileCreatePayload,
  TaskInboxSummary,
  TaskResponse,
  TaskResponseCreatePayload,
  TaskCreatePayload,
  TaskGroupAssignmentCreatePayload,
  TaskGroupAssignmentCreateResponse,
  TaskGroupReport,
  TaskUpdatePayload,
} from "../types/task";

export type TaskListScope =
  | "all"
  | "assigned_to_me"
  | "created_by_me"
  | "observed_by_me"
  | "awaiting_report"
  | "awaiting_acceptance";

export type TaskQuickStatus = "new" | "awaiting_report" | "awaiting_acceptance" | "overdue";

export type TaskParticipantRole = "assignee" | "creator";

export interface TaskListParams {
  organization_id?: string;
  chat_id?: string;
  status?: string;
  task_type?: string;
  scope?: TaskListScope;
  quick_status?: TaskQuickStatus;
  search?: string;
  task_number?: number;
  participant_role?: TaskParticipantRole;
  participant_user_id?: string;
  created_by_user_id?: string;
  assignee_id?: string;
  observer_id?: string;
  overdue?: boolean;
  due_today?: boolean;
  deadline_from?: string;
  deadline_to?: string;
  limit?: number;
  offset?: number;
}

export interface TaskInboxSummaryParams {
  organization_id?: string;
  chat_id?: string;
  status?: string;
  deadline_from?: string;
  deadline_to?: string;
}

export function getTasks(filters: TaskListParams = {}): Promise<Task[]> {
  return request<Task[]>("/tasks", { query: filters });
}

export function getTask(taskId: string): Promise<TaskDetails> {
  return request<TaskDetails>(`/tasks/${taskId}`);
}

export function createTask(payload: TaskCreatePayload): Promise<Task> {
  return request<Task>("/tasks", {
    method: "POST",
    body: payload,
  });
}

export function createGroupAssignment(
  payload: TaskGroupAssignmentCreatePayload,
): Promise<TaskGroupAssignmentCreateResponse> {
  return request<TaskGroupAssignmentCreateResponse>("/tasks/group-assignment", {
    method: "POST",
    body: payload,
  });
}

export function getGroupAssignmentReport(taskId: string): Promise<TaskGroupReport> {
  return request<TaskGroupReport>(`/tasks/${taskId}/group-report`);
}

export function updateTask(taskId: string, payload: TaskUpdatePayload): Promise<TaskDetails> {
  return request<TaskDetails>(`/tasks/${taskId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function addTaskAssignee(taskId: string, userId: string): Promise<TaskAssignee> {
  return request<TaskAssignee>(`/tasks/${taskId}/assignees`, {
    method: "POST",
    body: { user_id: userId },
  });
}

export function removeTaskAssignee(taskId: string, userId: string): Promise<void> {
  return request<void>(`/tasks/${taskId}/assignees/${userId}`, {
    method: "DELETE",
  });
}

export function cancelTask(taskId: string): Promise<TaskDetails> {
  return request<TaskDetails>(`/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

export function addComment(taskId: string, payload: TaskCommentCreatePayload): Promise<TaskComment> {
  return request<TaskComment>(`/tasks/${taskId}/comments`, {
    method: "POST",
    body: payload,
  });
}

export function getComments(taskId: string): Promise<TaskComment[]> {
  return request<TaskComment[]>(`/tasks/${taskId}/comments`);
}

export function addFile(taskId: string, payload: TaskFileCreatePayload): Promise<TaskFile> {
  return request<TaskFile>(`/tasks/${taskId}/files`, {
    method: "POST",
    body: payload,
  });
}

export function getFiles(taskId: string): Promise<TaskFile[]> {
  return request<TaskFile[]>(`/tasks/${taskId}/files`);
}

export function submitResponse(taskId: string, payload: TaskResponseCreatePayload): Promise<TaskResponse> {
  return request<TaskResponse>(`/tasks/${taskId}/responses`, {
    method: "POST",
    body: payload,
  });
}

export function acceptResponse(
  taskId: string,
  responseId: string,
  payload: TaskAcceptancePayload,
): Promise<TaskAcceptance> {
  return request<TaskAcceptance>(`/tasks/${taskId}/responses/${responseId}/accept`, {
    method: "POST",
    body: payload,
  });
}

export function rejectResponse(
  taskId: string,
  responseId: string,
  payload: TaskAcceptancePayload,
): Promise<TaskAcceptance> {
  return request<TaskAcceptance>(`/tasks/${taskId}/responses/${responseId}/reject`, {
    method: "POST",
    body: payload,
  });
}

export function getInboxSummary(params: TaskInboxSummaryParams = {}): Promise<TaskInboxSummary> {
  return request<TaskInboxSummary>("/tasks/inbox/summary", {
    query: params,
  });
}

export const listTasks = getTasks;
