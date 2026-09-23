import { useQuery } from "@tanstack/react-query";
import apiClient from "../service/api";
import { AlertsQueryParams, AlertsResponse } from "../types/alerts";

export const fetchUngroupedAlerts = async (params: AlertsQueryParams = {}): Promise<AlertsResponse> => {
  const {
    page = 1,
    page_size = 10,
    severity,
    triage_status,
    evaluation_status,
    name_contains,
    time_range,
    start_time,
    end_time,
    evaluation_score_operator,
    evaluation_score_value,
  } = params;

  const apiParams: any = {
    page,
    page_size,
    ungrouped_only: true, // Key parameter to fetch only ungrouped alerts
  };

  if (severity) {
    apiParams.severity = severity;
  }

  if (triage_status) {
    apiParams.triage_status = triage_status;
  }

  if (evaluation_status) {
    apiParams.evaluation_status = evaluation_status;
  }

  if (name_contains && name_contains.trim()) {
    apiParams.name_contains = name_contains.trim();
  }

  if (time_range) {
    apiParams.time_range = time_range;
  }

  if (time_range === 'custom') {
    if (start_time) {
      apiParams.start_time = start_time;
    }
    if (end_time) {
      apiParams.end_time = end_time;
    }
  }

  if (evaluation_score_operator && evaluation_score_value !== undefined) {
    apiParams.evaluation_score_operator = evaluation_score_operator;
    apiParams.evaluation_score_value = evaluation_score_value;
  }

  const response = await apiClient.get("/alerts", { params: apiParams });
  return response.data;
};

export const useUngroupedAlerts = (params: AlertsQueryParams = {}) => {
  return useQuery({
    queryKey: ['ungrouped-alerts', params],
    queryFn: () => fetchUngroupedAlerts(params),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
};
