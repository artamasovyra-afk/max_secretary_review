import { request } from "./client";
import type {
  BitrixRetryFailedResponse,
  BitrixSyncStatus,
  BitrixTaskSyncStatusResponse,
} from "../types/bitrix24";

interface BitrixTaskLinkApiResponse {
  bitrix_task_id: string | null;
  sync_status: BitrixSyncStatus;
  last_sync_at: string | null;
  last_error: string | null;
}

interface BitrixTaskSyncApiResponse {
  task_id: string;
  sync_status: BitrixSyncStatus;
  bitrix_task_id?: string | null;
  last_error?: string | null;
  link?: BitrixTaskLinkApiResponse | null;
}

interface BitrixRetryFailedApiResponse {
  results: BitrixTaskSyncApiResponse[];
}

export async function getBitrixTaskSyncStatus(
  taskId: string,
): Promise<BitrixTaskSyncStatusResponse> {
  const response = await request<BitrixTaskSyncApiResponse>(
    `/integrations/bitrix24/tasks/${taskId}/status`,
  );
  return normalizeTaskSyncStatus(response);
}

export async function syncBitrixTask(taskId: string): Promise<BitrixTaskSyncStatusResponse> {
  const response = await request<BitrixTaskSyncApiResponse>(
    `/integrations/bitrix24/tasks/${taskId}/sync`,
    {
      method: "POST",
    },
  );
  return normalizeTaskSyncStatus(response);
}

export async function retryFailedBitrixSync(
  limit?: number,
): Promise<BitrixRetryFailedResponse> {
  const response = await request<BitrixRetryFailedApiResponse>(
    "/integrations/bitrix24/retry-failed",
    {
      method: "POST",
      query: { limit },
    },
  );
  return summarizeRetryFailed(response.results);
}

function normalizeTaskSyncStatus(
  response: BitrixTaskSyncApiResponse,
): BitrixTaskSyncStatusResponse {
  return {
    task_id: response.task_id,
    bitrix_task_id: response.link?.bitrix_task_id ?? response.bitrix_task_id ?? null,
    sync_status: response.sync_status,
    last_sync_at: response.link?.last_sync_at ?? null,
    last_error: response.link?.last_error ?? response.last_error ?? null,
  };
}

function summarizeRetryFailed(results: BitrixTaskSyncApiResponse[]): BitrixRetryFailedResponse {
  return results.reduce<BitrixRetryFailedResponse>(
    (summary, result) => {
      summary.processed += 1;
      if (result.sync_status === "synced") {
        summary.synced += 1;
      }
      if (result.sync_status === "error") {
        summary.failed += 1;
      }
      if (result.sync_status === "disabled") {
        summary.disabled += 1;
      }
      return summary;
    },
    {
      processed: 0,
      synced: 0,
      failed: 0,
      disabled: 0,
    },
  );
}
