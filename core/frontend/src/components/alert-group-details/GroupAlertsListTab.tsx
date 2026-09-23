import { useState } from "react";
import { GroupAlertCard } from "./GroupAlertCard";
import { RemoveAlertsDialog } from "./RemoveAlertsDialog";

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

interface GroupAlertsListTabProps {
  alerts: Alert[];
  onAlertClick: (alertId: number) => void;
  onRemoveAlerts?: (alertIds: number[]) => Promise<void>;
  isTriaging?: boolean;
}

export function GroupAlertsListTab({
  alerts,
  onAlertClick,
  onRemoveAlerts,
  isTriaging = false
}: GroupAlertsListTabProps) {
  const [isRemoving, setIsRemoving] = useState(false);
  const [alertToRemove, setAlertToRemove] = useState<number | null>(null);
  const [showSingleRemoveDialog, setShowSingleRemoveDialog] = useState(false);

  const handleRemoveSingleAlert = (alertId: number) => {
    setAlertToRemove(alertId);
    setShowSingleRemoveDialog(true);
  };

  const handleSingleRemoveConfirm = async () => {
    if (!onRemoveAlerts || alertToRemove === null) return;

    setIsRemoving(true);
    try {
      await onRemoveAlerts([alertToRemove]);
      setAlertToRemove(null);
      setShowSingleRemoveDialog(false);
    } catch (error) {
      // Error handling is done in parent component
      setShowSingleRemoveDialog(false);
    } finally {
      setIsRemoving(false);
    }
  };

  // Check if removing a single alert would leave less than 2 alerts
  const canRemoveSingleAlert = alerts.length > 2;

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-2">
          Alerts in This Group ({alerts.length})
        </h2>
        <p className="text-sm text-muted-foreground">
          View detailed information for each alert in this group
        </p>
      </div>

      <div className="space-y-4">
        {alerts.map((alert) => (
          <GroupAlertCard
            key={alert.id}
            alert={alert}
            onViewAlert={onAlertClick}
            onRemoveAlert={onRemoveAlerts ? handleRemoveSingleAlert : undefined}
            canRemove={canRemoveSingleAlert && !isTriaging}
            isRemoving={isRemoving}
          />
        ))}
      </div>

      {/* Remove Single Alert Dialog */}
      <RemoveAlertsDialog
        open={showSingleRemoveDialog}
        onOpenChange={setShowSingleRemoveDialog}
        alertCount={1}
        onConfirm={handleSingleRemoveConfirm}
        isRemoving={isRemoving}
      />
    </div>
  );
}
