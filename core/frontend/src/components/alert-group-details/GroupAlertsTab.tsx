import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { SeverityChip, SeverityType } from "../severity-chip";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { cn } from "../ui/utils";
import { RemoveAlertsDialog } from "./RemoveAlertsDialog";
import { KeyValueCard } from "./KeyValueCard";
import { ChevronDown, ChevronRight, InfoIcon, TagIcon } from "lucide-react";

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

interface GroupAlertsTabProps {
  alerts: Alert[];
  onAlertClick: (alertId: number) => void;
  onRemoveAlerts?: (alertIds: number[]) => Promise<void>;
  isTriaging?: boolean;
}

export function GroupAlertsTab({ alerts, onAlertClick, onRemoveAlerts, isTriaging = false }: GroupAlertsTabProps) {
  const [isRemoving, setIsRemoving] = useState(false);
  const [alertToRemove, setAlertToRemove] = useState<number | null>(null);
  const [showSingleRemoveDialog, setShowSingleRemoveDialog] = useState(false);
  const [expandedAlertId, setExpandedAlertId] = useState<number | null>(null);

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

  const handleRowClick = (alertId: number) => {
    // Toggle expansion
    setExpandedAlertId(expandedAlertId === alertId ? null : alertId);
  };

  const handleViewAlert = (alertId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    onAlertClick(alertId);
  };

  // Check if removing a single alert would leave less than 2 alerts
  const canRemoveSingleAlert = alerts.length > 2;
  return (
    <Card style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-xl font-semibold mb-2">
            Alerts in This Group ({alerts.length})
          </h2>
          <p className="text-sm text-muted-foreground">
            Click on any alert row to expand and view detailed information
          </p>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12"></TableHead>
              <TableHead className="w-20">ID</TableHead>
              <TableHead>Alert Name</TableHead>
              <TableHead className="text-center w-32">Severity</TableHead>
              <TableHead className="text-center w-32">Status</TableHead>
              <TableHead className="w-40">Started At</TableHead>
              <TableHead className="w-32 text-center">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {alerts.map((alert) => {
              const isExpanded = expandedAlertId === alert.id;
              return (
                <>
                  <TableRow
                    key={alert.id}
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => handleRowClick(alert.id)}
                  >
                    <TableCell className="text-center">
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                    </TableCell>
                    <TableCell className="font-medium">
                      {alert.id}
                    </TableCell>
                    <TableCell className="font-medium">
                      {alert.alert_name}
                    </TableCell>
                    <TableCell className="text-center">
                      <SeverityChip severity={alert.severity as SeverityType} />
                    </TableCell>
                    <TableCell className="text-center">
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
                    </TableCell>
                    <TableCell className="text-sm text-secondary">
                      {new Date(alert.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleViewAlert(alert.id, e)}
                          className="h-8 px-3"
                        >
                          View
                        </Button>
                        {onRemoveAlerts && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemoveSingleAlert(alert.id)}
                            disabled={isTriaging || !canRemoveSingleAlert || isRemoving}
                            className="h-8 px-3 text-red-600 hover:bg-red-50 hover:text-red-700 disabled:text-muted-foreground"
                            title={!canRemoveSingleAlert
                              ? "Cannot remove: Group must have at least 2 alerts"
                              : "Remove this alert from the group"}
                          >
                            Remove
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>

                  {isExpanded && (
                    <TableRow key={`${alert.id}-expanded`}>
                      <TableCell colSpan={7} className="bg-muted/30 p-6">
                        <div className="space-y-4">
                          {/* Alert Overview Card */}
                          <Card className="box-shadow rounded-lg mr-2">
                            <CardHeader>
                              <CardTitle className="flex items-center gap-2 info-title-text">
                                <InfoIcon size={12} />
                                Alert Overview
                              </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              <div className="grid grid-cols-2 gap-6">
                                <div>
                                  <label className="text-sm font-medium text-tertiary">Alert Name</label>
                                  <p className="text-foreground">{alert.alert_name}</p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-tertiary">Alert Status</label>
                                  <p className="text-foreground capitalize">{alert.alert_status}</p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-tertiary">Severity</label>
                                  <div className="mt-1">
                                    <SeverityChip severity={alert.severity as SeverityType} />
                                  </div>
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-tertiary">Started At</label>
                                  <p className="text-foreground">
                                    {new Date(alert.created_at).toLocaleString('en-US', {
                                      month: 'short',
                                      day: 'numeric',
                                      year: 'numeric',
                                      hour: 'numeric',
                                      minute: '2-digit',
                                      hour12: true
                                    })}
                                  </p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-tertiary">Alert Source</label>
                                  <p className="text-foreground font-mono text-sm">{alert.alert_source}</p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium text-tertiary">Triage Status</label>
                                  <p className="text-foreground">Success</p>
                                </div>
                              </div>
                            </CardContent>
                          </Card>

                          {/* Labels Card */}
                          <KeyValueCard
                            title="Labels"
                            icon={TagIcon}
                            data={alert.labels || {}}
                          />

                          {/* Annotations Card */}
                          <KeyValueCard
                            title="Annotations"
                            icon={TagIcon}
                            data={alert.annotations || {}}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              );
            })}
          </TableBody>
        </Table>

        {/* Single Alert Remove Dialog */}
        <RemoveAlertsDialog
          open={showSingleRemoveDialog}
          onOpenChange={setShowSingleRemoveDialog}
          selectedCount={1}
          onConfirm={handleSingleRemoveConfirm}
          isRemoving={isRemoving}
        />
      </div>
    </Card>
  );
}
