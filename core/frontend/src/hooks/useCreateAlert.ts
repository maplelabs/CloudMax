import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiClient } from "../service/api";

interface ManualAlertCreateRequest {
  alert_name: string;
  severity: "P1" | "P2" | "P3";
  alert_status: "firing" | "resolved";
  description: string;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  trigger_triage?: boolean;
}

interface ManualAlertCreateResponse {
  success: boolean;
  message: string;
  alert_id: string;
  triage_triggered: boolean;
}

export function useCreateAlert() {
  const queryClient = useQueryClient();

  return useMutation<ManualAlertCreateResponse, Error, ManualAlertCreateRequest>({
    mutationFn: async (request: ManualAlertCreateRequest) => {
      const response = await apiClient.post("/alerts", request);
      return response.data;
    },
    onSuccess: (data) => {
      // Show success message - UI will display triage status separately
      toast.success(`Alert created successfully! ID: ${data.alert_id}`);

      // Invalidate all alerts queries to refresh the lists
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['ungrouped-alerts'] });
    },
    onError: (error: any) => {
      console.error("Failed to create alert:", error);

      // Differentiate error messages based on HTTP status
      const status = error.response?.status;
      const detail = error.response?.data?.detail;

      let errorMessage: string;
      if (status === 401) {
        errorMessage = "Authentication required. Please log in again.";
      } else if (status === 403) {
        errorMessage = "You don't have permission to create alerts.";
      } else if (status === 400) {
        errorMessage = detail || "Invalid alert data. Please check your inputs.";
      } else if (status === 500) {
        errorMessage = detail || "Server error. Please try again later.";
      } else {
        errorMessage = detail || error.message || "Failed to create alert. Please try again.";
      }

      toast.error(errorMessage);
    },
  });
}
