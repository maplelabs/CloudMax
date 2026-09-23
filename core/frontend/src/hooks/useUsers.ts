import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../service/api';
import { UsersQueryParams, User, UsersResponse } from '../types/users';

export const fetchUsers = async (params: UsersQueryParams = {}): Promise<UsersResponse> => {
  const {
    page = 1,
    page_size = 10,
    search,
    is_admin,
  } = params;

  const apiParams: any = {
    page,
    page_size,
  };

  if (search && search.trim()) {
    apiParams.search_string = search.trim();
  }

  if (is_admin !== undefined) {
    apiParams.role = is_admin ? 'admin' : 'user';
  }

  const response = await apiClient.get('/auth/users', {
    params: apiParams,
  });

  // API returns object with users array and pagination
  return response.data;
};

export const fetchUserById = async (id: number): Promise<User> => {
  const response = await apiClient.get(`/users/${id}/profile`);
  return response.data;
};

export const deleteUser = async (userId: number): Promise<void> => {
  await apiClient.delete(`/auth/users/${userId}`);
};

export const makeAdmin = async (userId: number): Promise<void> => {
  await apiClient.put(`/auth/users/${userId}/make-admin`);
};

export const removeAdmin = async (userId: number): Promise<void> => {
  await apiClient.put(`/auth/users/${userId}/remove-admin`);
};

export const addUser = async (userData: { email: string; username: string; password: string }): Promise<void> => {
  await apiClient.post('/auth/users/register', userData);
};

export const resetUserPassword = async (userId: number, newPassword: string): Promise<void> => {
  await apiClient.put(`/auth/users/${userId}/reset-password`, { new_password: newPassword });
};

// React Query hooks
export const useUsers = (params: UsersQueryParams = {}) => {
  return useQuery({
    queryKey: ['users', params],
    queryFn: () => fetchUsers(params),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
};

export const useUser = (id: number) => {
  return useQuery({
    queryKey: ['user', id],
    queryFn: () => fetchUserById(id),
    enabled: !!id,
    staleTime: 0,
    gcTime: 0,
  });
};

export const useDeleteUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error) => {
      console.error('Delete user mutation failed:', error);
    },
  });
};

export const useMakeAdmin = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: makeAdmin,
    onSuccess: (_, userId) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['user', userId] });
    },
    onError: (error) => {
      console.error('Make admin mutation failed:', error);
    },
  });
};

export const useRemoveAdmin = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeAdmin,
    onSuccess: (_, userId) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['user', userId] });
    },
    onError: (error) => {
      console.error('Remove admin mutation failed:', error);
    },
  });
};

export const useAddUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: addUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error) => {
      console.error('Add user mutation failed:', error);
    },
  });
};

export const useResetUserPassword = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, newPassword }: { userId: number; newPassword: string }) =>
      resetUserPassword(userId, newPassword),
    onSuccess: (_, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['user', userId] });
    },
    onError: (error) => {
      console.error('Reset user password mutation failed:', error);
    },
  });
};
