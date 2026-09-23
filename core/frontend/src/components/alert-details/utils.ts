import { StatusType } from "../status-chip";

// Helper function to format dates
export const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

// Helper function to map alert status to StatusType
export const mapAlertStatusToStatusType = (status: "firing" | "resolved" | "pending"): StatusType => {
  const statusMap: Record<"firing" | "resolved" | "pending", StatusType> = {
    "firing": "in-progress",
    "resolved": "success",
    "pending": "pending"
  };
  return statusMap[status];
};

// Helper function to format label keys from snake_case to Title Case
export const formatLabelKey = (key: string): string => {
  return key
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};
