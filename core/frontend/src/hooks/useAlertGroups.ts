import { useQuery } from "@tanstack/react-query";
import apiClient from "../service/api";

export interface AlertGroupsQueryParams {
  page?: number;
  page_size?: number;
  severity?: string;
  triage_status?: string;
  evaluation_status?: string;
  status?: string;
  name_contains?: string;
  evaluation_score_operator?: string;
  evaluation_score_value?: number;
  time_range?: string;
  start_time?: string;
  end_time?: string;
}

export interface AlertGroup {
  id: string;
  group_name: string;
  alert_count: number;
  severity: "P1" | "P2" | "P3";
  triage_status: string;
  status: string;
  grouping_confidence?: number;
  evaluation_score?: number | null;
  created_at: string;
  updated_at: string;
}

export interface AlertGroupsResponse {
  groups: AlertGroup[];
  pagination: {
    current_page: number;
    page_size: number;
    total_items: number;
  };
}

export const fetchAlertGroups = async (params: AlertGroupsQueryParams = {}): Promise<AlertGroupsResponse> => {
  const {
    page = 1,
    page_size = 10,
    severity,
    triage_status,
    evaluation_status,
    status,
    name_contains,
    evaluation_score_operator,
    evaluation_score_value,
    time_range,
    start_time,
    end_time,
  } = params;

  const apiParams: any = {
    page,
    page_size,
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

  if (status) {
    apiParams.status = status;
  }

  if (name_contains && name_contains.trim()) {
    apiParams.name_contains = name_contains.trim();
  }

  if (evaluation_score_operator && evaluation_score_value !== undefined) {
    apiParams.evaluation_score_operator = evaluation_score_operator;
    apiParams.evaluation_score_value = evaluation_score_value;
  }

  // Add time range filters
  if (time_range) {
    apiParams.time_range = time_range;
  }

  if (time_range === 'custom' && start_time && end_time) {
    apiParams.start_time = start_time;
    apiParams.end_time = end_time;
  }

  const response = await apiClient.get("/alert-groups", { params: apiParams });
  return response.data;
};

export const useAlertGroups = (params: AlertGroupsQueryParams = {}) => {
  return useQuery({
    queryKey: ['alert-groups', params],
    queryFn: () => fetchAlertGroups(params),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
};

// Fetch alert group details
export const fetchAlertGroupById = async (id: string): Promise<any> => {
  const response = await apiClient.get(`/alert-groups/${id}`);
  return response.data;
};

export const useAlertGroup = (id: string) => {
  return useQuery({
    queryKey: ['alert-group', id],
    queryFn: () => fetchAlertGroupById(id),
    enabled: !!id,
    staleTime: 0,
    gcTime: 0,
  });
};

// Fetch group triage journey
export const fetchGroupTriageJourney = async (groupId: string): Promise<any> => {
  const response = await apiClient.get(`/alert-groups/${groupId}/triage-journey`);
  return response.data;
};

export const useGroupTriageJourney = (groupId: string) => {
  return useQuery({
    queryKey: ['group-triage-journey', groupId],
    queryFn: () => fetchGroupTriageJourney(groupId),
    enabled: !!groupId,
    staleTime: 0,
    gcTime: 0,
  });
};

// Fetch group root cause analysis
export const fetchGroupRootCause = async (groupId: string): Promise<any> => {
  const response = await apiClient.get(`/alert-groups/${groupId}/root-cause`);
  return response.data;
};

export const useGroupRootCause = (groupId: string) => {
  return useQuery({
    queryKey: ['group-root-cause', groupId],
    queryFn: () => fetchGroupRootCause(groupId),
    enabled: !!groupId,
    staleTime: 0,
    gcTime: 0,
  });
};

// Fetch group evaluation
export const fetchGroupEvaluation = async (groupId: string): Promise<any> => {
  const response = await apiClient.get(`/alert-groups/${groupId}/evaluation`);
  return response.data;
};

export const useGroupEvaluation = (groupId: string) => {
  return useQuery({
    queryKey: ['group-evaluation', groupId],
    queryFn: () => fetchGroupEvaluation(groupId),
    enabled: !!groupId,
    staleTime: 0,
    gcTime: 0,
  });
};
