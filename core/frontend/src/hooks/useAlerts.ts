import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../service/api';
import { AlertsResponse, AlertsQueryParams, Alert, TriageResponse, RootCauseAnalysis, AlertEvaluation } from '../types/alerts';

export const fetchAlerts = async (params: AlertsQueryParams = {}): Promise<AlertsResponse> => {
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
    search,
    semantic_search
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

  if (name_contains && name_contains.trim()) {
    apiParams.name_contains = name_contains.trim();
  }

  if (time_range) {
    apiParams.time_range = time_range;
  }

  // Add custom time range parameters
  if (start_time) {
    apiParams.start_time = start_time;
  }

  if (end_time) {
    apiParams.end_time = end_time;
  }

  if (evaluation_score_operator) {
    apiParams.evaluation_score_operator = evaluation_score_operator;
  }

  if (evaluation_score_value !== null && evaluation_score_value !== undefined) {
    apiParams.evaluation_score_value = evaluation_score_value;
  }

  // Keep legacy search parameter for backward compatibility
  if (search && search.trim()) {
    apiParams.search_string = search.trim();
  }

  if (semantic_search) {
    apiParams.semantic_search = semantic_search;
  }

  const response = await apiClient.get('/alerts', {
    params: apiParams,
  });

  return response.data;
};

export const fetchAlertById = async (id: string): Promise<Alert> => {
  const response = await apiClient.get(`/alerts/${id}`);
  return response.data;
};

export const fetchTriage = async (alertId: string): Promise<TriageResponse> => {
  const response = await apiClient.get(`/alerts/${alertId}/triage`);
  return response.data;
};

export const fetchRootCauseAnalysis = async (alertId: string): Promise<RootCauseAnalysis> => {
  const response = await apiClient.get(`/alerts/${alertId}/root-cause`);
  return response.data;
};


export const fetchAlertEvaluation = async (alertId: string): Promise<AlertEvaluation> => {
  const response = await apiClient.get(`/alerts/${alertId}/evaluation`);
  return response.data;
};

export const startTriage = async (alertId: string): Promise<any> => {
  const response = await apiClient.post(`/alerts/${alertId}/triage`);
  return response.data;
};

export const stopTriage = async (alertId: string): Promise<any> => {
  const response = await apiClient.delete(`/alerts/${alertId}/triage`);
  return response.data;
};

// React Query hooks
export const useAlerts = (params: AlertsQueryParams = {}) => {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => fetchAlerts(params),
    staleTime:0,
    gcTime: 0,
    retry: 1,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
};

export const useAlert = (id: string) => {
  return useQuery({
    queryKey: ['alert', id],
    queryFn: () => fetchAlertById(id),
    enabled: !!id,
    staleTime: 0, // No caching - always fetch fresh data
    gcTime: 0, // Don't keep in cache
    //refetchInterval: 5000, // Auto-refresh every 5 seconds
  });
};

export const useTriage = (alertId: string) => {
  return useQuery({
    queryKey: ['triage', alertId],
    queryFn: () => fetchTriage(alertId),
    enabled: !!alertId,
    staleTime: 0, // No caching - always fetch fresh data
    gcTime: 0, // Don't keep in cache
    retry: false, // Don't retry on error
    throwOnError: false, // Don't throw errors - handle gracefully
    //refetchInterval: 5000, // Auto-refresh every 5 seconds
  });
};

export const useRootCauseAnalysis = (alertId: string) => {
  return useQuery({
    queryKey: ['root-cause', alertId],
    queryFn: () => fetchRootCauseAnalysis(alertId),
    enabled: !!alertId,
    staleTime: 0, // No caching - always fetch fresh data
    gcTime: 0, // Don't keep in cache
    retry: false, // Don't retry on error
    throwOnError: false, // Don't throw errors - handle gracefully
    //refetchInterval: 5000, // Auto-refresh every 5 seconds
  });
};

export const useAlertEvaluation = (alertId: string) => {
  return useQuery({
    queryKey: ['alert-evaluation', alertId],
    queryFn: () => fetchAlertEvaluation(alertId),
    enabled: !!alertId,
    staleTime: 0, // No caching - always fetch fresh data
    gcTime: 0, // Don't keep in cache
    retry: false, // Don't retry on error
    throwOnError: false, // Don't throw errors - handle gracefully
    //refetchInterval: 5000, // Auto-refresh every 5 seconds
  });
};

export const useStartTriage = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: startTriage,
    onSuccess: (data, alertId) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['alert', alertId] });
      queryClient.invalidateQueries({ queryKey: ['triage', alertId] });
    },
    onError: (error) => {
      console.error('Start triage mutation failed:', error);
    },
  });
};

export const useStopTriage = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: stopTriage,
    onSuccess: (data, alertId) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['alert', alertId] });
      queryClient.invalidateQueries({ queryKey: ['triage', alertId] });
    },
    onError: (error) => {
      console.error('Stop triage mutation failed:', error);
    },
  });
};
