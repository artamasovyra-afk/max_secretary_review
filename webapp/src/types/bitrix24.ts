export type BitrixSyncStatus = "pending" | "synced" | "error" | "disabled";

export interface BitrixTaskSyncStatusResponse {
  task_id: string;
  bitrix_task_id: string | null;
  sync_status: BitrixSyncStatus;
  last_sync_at: string | null;
  last_error: string | null;
}

export interface BitrixRetryFailedResponse {
  processed: number;
  synced: number;
  failed: number;
  disabled: number;
}
