import { InfoIcon, TagIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { SeverityChip, SeverityType } from "../severity-chip";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { cn } from "../ui/utils";

interface Alert {
  id: number;
  alert_name: string;
  severity: string;
  alert_status: string;
  alert_source: string;
  created_at: string;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
}

interface GroupAlertCardProps {
  alert: Alert;
  onViewAlert: (alertId: number) => void;
  onRemoveAlert?: (alertId: number) => void;
  canRemove?: boolean;
  isRemoving?: boolean;
}

export function GroupAlertCard({
  alert,
  onViewAlert,
  onRemoveAlert,
  canRemove = true,
  isRemoving = false
}: GroupAlertCardProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  return (
    <Card className="box-shadow rounded-lg">
      {/* Alert Overview */}
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 info-title-text">
            <InfoIcon size={12} />
            Alert Overview
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onViewAlert(alert.id)}
              className="h-8 px-3"
            >
              View
            </Button>
            {onRemoveAlert && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onRemoveAlert(alert.id)}
                disabled={!canRemove || isRemoving}
                className="h-8 px-3 text-red-600 hover:bg-red-50 hover:text-red-700 disabled:text-muted-foreground"
                title={!canRemove ? "Cannot remove: Group must have at least 2 alerts" : "Remove this alert from the group"}
              >
                Remove
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="text-sm font-medium text-tertiary">Alert Name</label>
            <p className="text-foreground">{alert.alert_name}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Alert Status</label>
            <div className="mt-1">
              <Badge
                variant="secondary"
                className={cn(
                  "capitalize",
                  alert.alert_status === "firing" && "bg-red-100 text-red-700 border-red-300",
                  alert.alert_status === "resolved" && "bg-green-100 text-green-700 border-green-300"
                )}
              >
                {alert.alert_status}
              </Badge>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Severity</label>
            <div className="mt-1">
              <SeverityChip severity={alert.severity as SeverityType} />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Started At</label>
            <p className="text-foreground">{formatDate(alert.created_at)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Alert Source</label>
            <p className="text-foreground font-mono text-sm">{alert.alert_source}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Alert ID</label>
            <p className="text-foreground">#{alert.id}</p>
          </div>
        </div>
      </CardContent>

      {/* Labels */}
      {alert.labels && Object.keys(alert.labels).length > 0 && (
        <>
          <CardHeader className="pt-0">
            <CardTitle className="flex items-center gap-2 info-title-text">
              <TagIcon size={12} />
              Labels
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="grid grid-cols-2 gap-4">
              {Object.entries(alert.labels).map(([key, value]) => (
                <div key={key}>
                  <label className="label-title-text">{key}</label>
                  <p className="label-value-text label-title-text mt-1 break-all">{value}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </>
      )}
    </Card>
  );
}
