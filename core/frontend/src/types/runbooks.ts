export interface Runbook {
  id: string;
  name: string;
  source_type: 'file' | 'confluence';
  created_at: string;
  updated_at: string;
  content_size_bytes: number;
  similarity_score?: number; // Only present in search results
}



// Bulk Delete Types
export interface BulkDeleteRequest {
  runbook_ids: string[];
}

export interface BulkDeleteResult {
  runbook_id: string;
  runbook_title: string;
  status: 'success' | 'error';
  error_message?: string;
}

export interface BulkDeleteResponse {
  total_requested: number;
  successful_deletes: number;
  failed_deletes: number;
  results: BulkDeleteResult[];
  summary: string;
}

export interface Pagination {
  current_page: number;
  page_size: number;
  total_items: number;
}

export interface RunbooksResponse {
  runbooks: Runbook[];
  pagination: Pagination;
}

export interface RunbooksQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
  semantic_search?: boolean;
}


// Confluence Integration Types

export interface ConfluenceImportRequest {
  page_url: string;
  include_children: boolean;
  max_depth: number;
  max_pages: number;
}

export interface ConfluenceImportedPage {
  title: string;
  runbook_id: string;
  page_id: string;
  url: string;
  status: 'success' | 'error' | 'updated';
  error?: string;
}

export interface ConfluenceImportResponse {
  parent_page: ConfluenceImportedPage;
  child_pages: ConfluenceImportedPage[];
  total_imported: number;
  total_failed: number;
}

export interface ConfluenceValidationRequest {
  base_url: string;
  username: string;
  api_token: string;
}

export interface ConfluenceValidationResponse {
  status: 'success' | 'error';
  user?: string;
  error?: string;
}
