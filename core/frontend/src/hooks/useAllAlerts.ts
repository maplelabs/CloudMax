import { useQuery } from "@tanstack/react-query";
import apiClient from "../service/api";
import { AlertListResponse } from "../types/alerts";

interface UseAllAlertsParams {
  page?: number;
  page_size?: number;
  severity?: string;
  alert_status?: string;
  triage_status?: string;
  evaluation_status?: string;
  time_range?: string;
  start_time?: string;
  end_time?: string;
  evaluation_score_operator?: string;
  evaluation_score_value?: number;
}

export function useAllAlerts(params: UseAllAlertsParams) {
  return useQuery<AlertListResponse>({
    queryKey: ["all-alerts", params],
    queryFn: async () => {
      const response = await apiClient.get("/alerts/all", {
        params: {
          ...params,
          include_grouped: true, // Include both grouped and ungrouped alerts
        },
      });
      return response.data;
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}
