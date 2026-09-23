import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../service/api';
import { RunbooksResponse, RunbooksQueryParams, BulkDeleteResponse } from '../types/runbooks';

export const fetchRunbooks = async (params: RunbooksQueryParams = {}): Promise<RunbooksResponse> => {
  const { page = 1, page_size = 10, search, semantic_search } = params;

  const apiParams: any = {
    page,
    page_size,
  };

  if (search && search.trim()) {
    apiParams.search_string = search.trim();
  }

  if (semantic_search) {
    apiParams.semantic_search = semantic_search;
  }

  const response = await apiClient.get('/runbooks', {
    params: apiParams,
  });

  return response.data;
};

export const fetchRunbookById = async (id: string) => {
  const response = await apiClient.get(`/runbooks/${id}`);
  const runbook = response.data;

  // Calculate approximate size if content is available
  if (runbook.content) {
    const sizeInBytes = new Blob([runbook.content]).size;
    runbook.size = formatFileSize(sizeInBytes);
  }

  return runbook;
};

export const deleteRunbook = async (id: string): Promise<void> => {
  await apiClient.delete(`/runbooks/${id}`);
};

export const bulkDeleteRunbooks = async (runbookIds: string[]): Promise<BulkDeleteResponse> => {
  const response = await apiClient.post('/runbooks/bulk-delete', {
    runbook_ids: runbookIds
  });
  return response.data;
};

export const uploadRunbook = async (
  formData: FormData,
  onUploadProgress?: (progressEvent: any) => void
): Promise<any> => {
  const response = await apiClient.post('/runbooks', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress,
  });
  return response.data;
};

// Utility function to format file size
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};


export const useRunbooks = (params: RunbooksQueryParams = {}) => {
  return useQuery({
    queryKey: ['runbooks', params],
    queryFn: () => fetchRunbooks(params),
    staleTime: params.search ? 30 * 1000 : 5 * 60 * 1000, // Shorter cache for search results
    gcTime: 10 * 60 * 1000,
    retry: 1,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
};

export const useRunbook = (id: string) => {
  return useQuery({
    queryKey: ['runbook', id],
    queryFn: () => fetchRunbookById(id),
    enabled: !!id, // avoids running the query if id is undefined/null
    staleTime: 5 * 60 * 1000,
  });
};

export const useDeleteRunbook = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteRunbook,
    onSuccess: () => {
      // Invalidate and refetch runbooks list
      queryClient.invalidateQueries({ queryKey: ['runbooks'] });
    },
    onError: (error) => {
      console.error('Delete runbook mutation failed:', error);
    },
  });
};

export const useBulkDeleteRunbooks = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: bulkDeleteRunbooks,
    onSuccess: () => {
      // Invalidate and refetch runbooks list
      queryClient.invalidateQueries({ queryKey: ['runbooks'] });
    },
    onError: (error) => {
      console.error('Bulk delete runbooks mutation failed:', error);
    },
  });
};

export const updateRunbook = async (id: string, updateData: { title?: string; content?: string }): Promise<any> => {
  const response = await apiClient.put(`/runbooks/${id}`, updateData);
  return response.data;
};

export const useUploadRunbook = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ formData, onUploadProgress }: { formData: FormData; onUploadProgress?: (progressEvent: any) => void }) =>
      uploadRunbook(formData, onUploadProgress),
    onSuccess: () => {
      // Invalidate and refetch runbooks list
      queryClient.invalidateQueries({ queryKey: ['runbooks'] });
    },
    onError: (error) => {
      console.error('Upload runbook mutation failed:', error);
    },
  });
};

export const useUpdateRunbook = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, updateData }: { id: string; updateData: { title?: string; content?: string } }) =>
      updateRunbook(id, updateData),
    onSuccess: (data, variables) => {
      // Invalidate and refetch runbooks list and individual runbook
      queryClient.invalidateQueries({ queryKey: ['runbooks'] });
      queryClient.invalidateQueries({ queryKey: ['runbook', variables.id] });
    },
    onError: (error) => {
      console.error('Update runbook mutation failed:', error);
    },
  });
};


// Confluence Integration API functions

export const validateConfluenceCredentials = async (
  request: import('../types/runbooks').ConfluenceValidationRequest
): Promise<import('../types/runbooks').ConfluenceValidationResponse> => {
  const response = await apiClient.post('/runbooks/validate-confluence', request);
  return response.data;
};

export const importFromConfluence = async (
  request: import('../types/runbooks').ConfluenceImportRequest
): Promise<import('../types/runbooks').ConfluenceImportResponse> => {
  const response = await apiClient.post('/runbooks/import-confluence', request);
  return response.data;
};

export const syncConfluenceRunbooks = async (): Promise<{ status: string; job_id: string; message: string }> => {
  const response = await apiClient.post('/runbooks/sync-confluence');
  return response.data;
};

// Confluence React Query hooks

export const useValidateConfluence = () => {
  return useMutation({
    mutationFn: validateConfluenceCredentials,
  });
};

export const useImportConfluence = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: importFromConfluence,
    onSuccess: () => {
      // Invalidate runbooks query to refetch the list
      queryClient.invalidateQueries({ queryKey: ['runbooks'] });
    },
  });
};

export const useSyncConfluence = () => {
  return useMutation({
    mutationFn: syncConfluenceRunbooks,
  });
};
