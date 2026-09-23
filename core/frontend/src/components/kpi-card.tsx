import { Card } from "./ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { LucideIcon, InfoIcon } from "lucide-react";
import { cn } from "./ui/utils";
import { BellIcon, ClockIcon, DollerSignIcon, HatchIcon } from "../icons";

interface KpiCardProps {
  label: string;
  value: string | number;
  delta?: {
    value: number;
    isPositive?: boolean;
    period?: string;
  };
  tooltip?: string;
  className?: string;
  icon?: LucideIcon;
}

export function KpiCard({ label, value, delta, tooltip, className, icon }: KpiCardProps) {
  // Auto-select icon based on label if not provided
  const IconComponent = icon || getIconForLabel(label);

  return (
    <Card className={cn("p-6 min-w-60", className)}>
      <div className="flex items-center justify-between ">
        <div className="space-y-3 flex-1">
                    {/* Label with optional tooltip */}
          <div className="flex items-center gap-1.5">
                    {IconComponent && (
          <div className="flex items-center">
            <IconComponent className="text-secondary" />
          </div>
        )}
            <span className="kpi-tile-header text-tertiary">{label}</span>
            {tooltip && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <InfoIcon className="h-4 w-4 mt-1 text-muted text-xs"/>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="max-w-xs text-sm text-white">{tooltip}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
          {/* Primary Value */}
          <div className="flex items-center gap-2 -mt-10">
            <div className="kpi-tile-value text-secondary">{value}</div>
            {delta && delta.value !== 0 && (
              <span className={cn(
                "text-xl font-medium",
                delta.value > 0? "text-success" : "text-danger"
              )}>
                {delta.value > 0 ? "↑" : "↓"} {Math.abs(delta.value)}%
              </span>
            )}
          </div>
        </div>

        {/* Icon on the right */}

      </div>
    </Card>
  );
}

// Helper function to auto-select icon based on label
function getIconForLabel(label: string) {
  
  const lowerLabel = label.toLowerCase();

  if (lowerLabel.includes('alert')) return BellIcon;
  if (lowerLabel.includes('cost')) return DollerSignIcon;
  if (lowerLabel.includes('calls')) return HatchIcon;
  if (lowerLabel.includes('latency')) return ClockIcon;
  if (lowerLabel.includes('success') || lowerLabel.includes('rate')) return HatchIcon;
  if (lowerLabel.includes('score') || lowerLabel.includes('evaluation')) return DollerSignIcon;

  return HatchIcon; // default icon
}