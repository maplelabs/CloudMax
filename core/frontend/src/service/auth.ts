import axios from 'axios';
import { API_BASE_URL } from '../utils/config';

interface LoginCredentials {
  email: string;
  password: string;
}

interface RegisterCredentials {
  email: string;
  username: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id?: string;
}

interface RefreshTokenRequest {
  refresh_token: string;
}

interface UpdatePasswordRequest {
  old_password: string;
  new_password: string;
}

export interface UserProfile {
  id: string;
  email: string;
  username: string;
  is_admin?: boolean;
  created_at?: string;
  updated_at?: string;
}

// Token management
export const tokenManager = {
  getAccessToken: (): string | null => {
    return localStorage.getItem('access_token');
  },

  getRefreshToken: (): string | null => {
    return localStorage.getItem('refresh_token');
  },

  setTokens: (accessToken: string, refreshToken: string, userId?: string): void => {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    localStorage.setItem('isAuthenticated', 'true');
    if (userId) {
      localStorage.setItem('user_id', userId);
    }
  },

  clearTokens: (): void => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('isAuthenticated');
    localStorage.removeItem('user_id');
    // Also clear old auth credentials if they exist
    localStorage.removeItem('auth_credentials');
  },

  isAuthenticated: (): boolean => {
    return !!tokenManager.getAccessToken();
  }
};

// Auth API calls
export const authService = {
  register: async (credentials: RegisterCredentials): Promise<void> => {
    try {
      await axios.post(
        `${API_BASE_URL}/auth/users/register`,
        credentials,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );
    } catch (error: any) {
      if (error.response?.status === 400) {
        throw new Error(error.response?.data?.detail || 'User already exists or invalid data');
      }
      throw new Error(error.response?.data?.detail || 'Registration failed. Please try again.');
    }
  },

  login: async (credentials: LoginCredentials): Promise<TokenResponse> => {
    try {
      const response = await axios.post<TokenResponse>(
        `${API_BASE_URL}/auth/users/login`,
        credentials,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      // Store tokens and user_id if available
      tokenManager.setTokens(response.data.access_token, response.data.refresh_token, response.data.user_id);

      return response.data;
    } catch (error: any) {
      if (error.response?.status === 401) {
        throw new Error('Invalid email or password');
      }
      throw new Error(error.response?.data?.detail || 'Login failed. Please try again.');
    }
  },

  logout: async (): Promise<void> => {
    try {
      const accessToken = tokenManager.getAccessToken();
      
      if (accessToken) {
        // Call logout endpoint
        await axios.post(
          `${API_BASE_URL}/auth/users/logout`,
          {},
          {
            headers: {
              'Authorization': `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
          }
        );
      }
    } catch (error) {
      // Even if the API call fails, we still want to clear local tokens
      console.error('Logout API call failed:', error);
    } finally {
      // Always clear tokens on logout
      tokenManager.clearTokens();
    }
  },

  refreshToken: async (): Promise<TokenResponse> => {
    const refreshToken = tokenManager.getRefreshToken();

    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    try {
      const response = await axios.post<TokenResponse>(
        `${API_BASE_URL}/auth/users/refresh?refresh_token=${refreshToken}`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      // Update tokens
      tokenManager.setTokens(response.data.access_token, response.data.refresh_token);

      return response.data;
    } catch (error: any) {
      // If refresh fails, clear tokens and force re-login
      tokenManager.clearTokens();
      throw new Error('Session expired. Please login again.');
    }
  },

  getUserProfile: async (userId: string): Promise<UserProfile> => {
    // Dynamically import apiClient to avoid circular dependency
    // This allows the token refresh interceptor to work
    const { apiClient } = await import('./api');

    try {
      const response = await apiClient.get<UserProfile>(`/users/${userId}/profile`);
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to fetch user profile.');
    }
  },

  updatePassword: async (passwords: UpdatePasswordRequest): Promise<void> => {
    // Dynamically import apiClient to avoid circular dependency
    // This allows the token refresh interceptor to work
    const { apiClient } = await import('./api');
    try {
      await apiClient.put('/auth/users/update-password', passwords);
    } catch (error: any) {
      if (error.response?.status === 400) {
        throw new Error(error.response?.data?.detail || 'Invalid old password or password requirements not met.');
      }
      throw new Error(error.response?.data?.detail || 'Failed to update password.');
    }
  }
};

