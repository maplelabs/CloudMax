export interface User {
  id: number;
  email: string;
  username: string;
  admin: boolean;
  created_at: string;
  updated_at: string;
}

export interface Pagination {
  current_page: number;
  page_size: number;
  total_items: number;
}

export interface UsersResponse {
  users: User[];
  pagination: Pagination;
}

export interface UsersQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
  is_admin?: boolean;
}
