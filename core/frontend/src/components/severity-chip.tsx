import { cn } from "./ui/utils";

export type SeverityType = "P1" | "P2" | "P3";

interface SeverityChipProps {
  severity: SeverityType;
  className?: string;
}

const severityConfig = {
  "P1": {
    label: "P1",
    dotClass: "severity-p1-dot"
  },
  "P2": {
    label: "P2",
    dotClass: "severity-p2-dot"
  },
  "P3": {
    label: "P3",
    dotClass: "severity-p3-dot"
  }
};

export function SeverityChip({ severity, className }: SeverityChipProps) {
  const config = severityConfig[severity];
  
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-2",
        "text-secondary  border-medium",
        className
      )}
    >
      <span
        className={cn("w-2 h-2 rounded-full", config.dotClass)}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}