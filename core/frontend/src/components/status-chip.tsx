import { LoaderIcon } from "../icons";
import { cn } from "./ui/utils";
import { CheckCircle2, AlertCircle, Clock, List } from "lucide-react";

export type StatusType = "not-started" | "in-progress" | "in_progress" | "success" | "failed" | "processing" | "pending" | "error" | "queued" | "completed";

interface StatusChipProps {
  status: StatusType;
  className?: string;
}

const statusConfig: Record<StatusType, {
  label: string;
  chipClass: string;
  icon?: React.ElementType;
  iconClass?: string;
}> = {
  "not-started": {
    label: "Not Started",
    chipClass: "status-not-started",
    icon: Clock,
    iconClass: "status-not-started-icon"
  },
  "in-progress": {
    label: "Processing",
    chipClass: "status-in-progress",
    icon: LoaderIcon,
    iconClass: "status-in-progress-icon"
  },
  "in_progress": {
    label: "Processing",
    chipClass: "status-in-progress",
    icon: LoaderIcon,
    iconClass: "status-in-progress-icon"
  },
  "success": {
    label: "Success",
    chipClass: "status-success",
    icon: CheckCircle2,
    iconClass: "status-success-icon"
  },
  "failed": {
    label: "Failed",
    chipClass: "status-failed",
    icon: AlertCircle,
    iconClass: "status-failed-icon"
  },
  "processing": {
    label: "Processing",
    chipClass: "status-in-progress",
    icon: LoaderIcon,
    iconClass: "status-in-progress-icon"
  },
  "pending": {
    label: "Pending",
    chipClass: "status-not-started",
    icon: Clock,
    iconClass: "status-not-started-icon"
  },
  "error": {
    label: "Error",
    chipClass: "status-failed",
    icon: AlertCircle,
    iconClass: "status-failed-icon"
  },
  "queued": {
    label: "Queued",
    chipClass: "status-queued",
    icon: List,
    iconClass: "status-queued-icon"
  },
  "completed": {
    label: "Completed",
    chipClass: "status-success",
    icon: CheckCircle2,
    iconClass: "status-success-icon"
  }
};

export function StatusChip({ status, className }: StatusChipProps) {
  // Handle null/undefined status
  if (!status) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium",
          "text-secondary bg-surface-secondary border-medium",
          className
        )}
        style={{width:"75px"}}
      >
        <span
          className="w-2 h-2 rounded-full bg-muted"
          aria-hidden="true"
        />
        No Status
      </span>
    );
  }

  const config = statusConfig[status as StatusType];

  if (!config) {
    console.error(`Unknown status: "${status}". Available statuses:`, Object.keys(statusConfig));
    // Fallback to a neutral appearance
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium",
          "text-secondary bg-surface-secondary border-medium",
          className
        )}
        style={{width:"75px"}}
      >
        <Clock className="w-3 h-3" aria-hidden="true" />
        Unknown: {status}
      </span>
    );
  }

  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium",
        config.chipClass,
        className
      )}
      style={{width:"95px"}}
    >
      {Icon && (
        <Icon
          className={cn("w-3 h-3", config.iconClass)}
          aria-hidden="true"
        />
      )}
      {config.label}
    </span>
  );
}