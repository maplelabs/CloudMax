import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiConfigResponse, TestConnectionRequest, TestConnectionResponse } from '../types/config';
import apiClient from '../service/api';

const configApi = {
  get: (): Promise<{ data: ApiConfigResponse }> => apiClient.get('/config'),
  post: (config: ApiConfigResponse) => apiClient.post('/config', config),
  update: (config: Partial<ApiConfigResponse>) => apiClient.put('/config', config),
  testConnection: (connectionData: TestConnectionRequest): Promise<{ data: TestConnectionResponse }> =>
    apiClient.post('/config/test-connection', connectionData),
};


const QUERY_KEY = ['config'];

// Fetch configuration
const fetchConfig = async (): Promise<ApiConfigResponse> => {
  const response = await configApi.get();
  return response.data;
};

// Create configuration
const createConfig = async (config: ApiConfigResponse): Promise<void> => {
  await configApi.post(config);
};

// Update configuration
const updateConfig = async (config: Partial<ApiConfigResponse>): Promise<void> => {
  await configApi.update(config);
};

export const useConfig = () => {
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchConfig,
    staleTime: 5000, // 5 seconds (refresh more frequently for config changes)
    gcTime: 300000, // 5 minutes (formerly cacheTime)
    refetchOnWindowFocus: true, // Refetch when user returns to the tab
    retry: 2,
  });

  return {
    ...query,
    config: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};

export const useCreateConfig = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createConfig,
    onSuccess: () => {
      // Invalidate and refetch config after successful creation
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (error) => {
      console.error('Failed to create configuration:', error);
    },
  });
};

export const useUpdateConfig = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateConfig,
    onSuccess: () => {
      // Invalidate and refetch config after successful update
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (error) => {
      console.error('Failed to update configuration:', error);
    },
  });
};

// Hook for testing connections
export const useTestConnection = () => {
  return useMutation({
    mutationFn: (connectionData: TestConnectionRequest) => configApi.testConnection(connectionData),
    onError: (error) => {
      console.error('Failed to test connection:', error);
    },
  });
};

// Hook for optimistic updates (optional, for better UX)
export const useOptimisticUpdateConfig = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateConfig,
    onMutate: async (newConfig) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });

      // Snapshot the previous value
      const previousConfig = queryClient.getQueryData<ApiConfigResponse>(QUERY_KEY);

      // Optimistically update to the new value
      if (previousConfig) {
        queryClient.setQueryData<ApiConfigResponse>(QUERY_KEY, {
          ...previousConfig,
          ...newConfig,
        });
      }

      // Return a context object with the snapshotted value
      return { previousConfig };
    },
    onError: (err, newConfig, context) => {
      // If the mutation fails, use the context returned from onMutate to roll back
      if (context?.previousConfig) {
        queryClient.setQueryData(QUERY_KEY, context.previousConfig);
      }
    },
    onSettled: () => {
      // Always refetch after error or success
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
};