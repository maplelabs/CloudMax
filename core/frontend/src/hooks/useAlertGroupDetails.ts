import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "../service/api";

// Types for Alert Group Details
export interface AlertGroupDetail {
  id: number;
  group_name: string;
  severity: "P1" | "P2" | "P3";
  triage_status: string;
  status: string;
  grouping_confidence: number;
  grouping_reasoning: string;
  thread_id?: string;
  created_at: string;
  updated_at: string;
  alerts: Array<{
    id: number;
    alert_name: string;
    severity: string;
    alert_source: string;
    created_at: string;
  }>;
}

export interface TriageJourney {
  alert_id: string;
  messages: Array<{
    role: string;
    content: string;
    timestamp?: string;
    tool_calls?: any[];
  }>;
}

export interface RootCauseAnalysis {
  content: string;
}

export interface GroupEvaluation {
  average_score_percent: number;
  reason: string;
  score_criteria_cards: Array<{
    title: string;
    score_percent: number;
    description: string;
  }>;
}

// Fetch functions
export const fetchAlertGroupById = async (id: string): Promise<AlertGroupDetail> => {
  const response = await apiClient.get(`/alert-groups/${id}`);
  return response.data;
};

export const fetchGroupTriage = async (groupId: string): Promise<TriageJourney> => {
  const response = await apiClient.get(`/alert-groups/${groupId}/triage`);
  return response.data;
};

export const fetchGroupRootCause = async (groupId: string): Promise<RootCauseAnalysis> => {
  const response = await apiClient.get(`/alert-groups/${groupId}/root-cause`);
  return response.data;
};

export const fetchGroupEvaluation = async (groupId: string): Promise<GroupEvaluation> => {
  const response = await apiClient.get(`/alert-groups/${groupId}/evaluation`);
  return response.data;
};

export const addAlertsToGroup = async (groupId: string, alertIds: string[]) => {
  const response = await apiClient.post(`/alert-groups/${groupId}/add-alerts`, {
    alert_ids: alertIds
  });
  return response.data;
};

export const startGroupTriage = async (groupId: string) => {
  const response = await apiClient.post(`/alert-groups/${groupId}/triage`);
  return response.data;
};

export const triggerGroupEvaluation = async (groupId: string) => {
  const response = await apiClient.post(`/alert-groups/${groupId}/evaluation`);
  return response.data;
};

// React Query hooks
export const useAlertGroupDetail = (id: string) => {
  return useQuery({
    queryKey: ['alert-group', id],
    queryFn: () => fetchAlertGroupById(id),
    enabled: !!id,
    staleTime: 0,
    gcTime: 0,
  });
};

export const useGroupTriage = (groupId: string) => {
  return useQuery({
    queryKey: ['group-triage', groupId],
    queryFn: () => fetchGroupTriage(groupId),
    enabled: !!groupId,
    staleTime: 0,
    gcTime: 0,
  });
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

export const useGroupEvaluation = (groupId: string) => {
  return useQuery({
    queryKey: ['group-evaluation', groupId],
    queryFn: () => fetchGroupEvaluation(groupId),
    enabled: !!groupId,
    staleTime: 0,
    gcTime: 0,
  });
};

export const useAddAlertsToGroup = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ groupId, alertIds }: { groupId: string; alertIds: string[] }) =>
      addAlertsToGroup(groupId, alertIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['alert-group', variables.groupId] });
      queryClient.invalidateQueries({ queryKey: ['ungrouped-alerts'] });
      queryClient.invalidateQueries({ queryKey: ['alert-groups'] });
    },
  });
};

export const useStartGroupTriage = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (groupId: string) => startGroupTriage(groupId),
    onSuccess: (_, groupId) => {
      queryClient.invalidateQueries({ queryKey: ['alert-group', groupId] });
      queryClient.invalidateQueries({ queryKey: ['group-triage', groupId] });
    },
  });
};
