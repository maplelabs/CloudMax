import { useState, useMemo } from "react";
import { TimeRange } from "../time-range-selector";
import { StatusChip, StatusType } from "../status-chip";
import { SeverityChip, SeverityType } from "../severity-chip";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Card } from "../ui/card";
import { Checkbox } from "../ui/checkbox";
import { Search, Loader2, Play, AlertCircle, Layers } from "lucide-react";
import { cn } from "../ui/utils";
import { useUngroupedAlerts } from "../../hooks/useUngroupedAlerts";
import { useStartTriage } from "../../hooks/useAlerts";
import { Alert as AlertType, AlertsQueryParams } from "../../types/alerts";
import { toast } from "sonner";
import { useConfig } from "../../hooks/useConfig";
import apiClient from "../../service/api";
import { CreateGroupDialog } from "./CreateGroupDialog";
import { AddToGroupDialog } from "./AddToGroupDialog";
import { useAlertGroups } from "../../hooks/useAlertGroups";

interface AlertsTabContentProps {
  timeRange: TimeRange;
  customTimeRange?: { start: Date; end: Date };
  onAlertClick?: (alert: AlertType) => void;
}

export function AlertsTabContent({ timeRange, customTimeRange, onAlertClick }: AlertsTabContentProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityType | "all">("all");
  const [triageStatusFilter, setTriageStatusFilter] = useState<StatusType | "all">("all");
  const [scoreRange, setScoreRange] = useState<string>("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [triggeringTriage, setTriggeringTriage] = useState<string | null>(null);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set());
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showAddToGroupDialog, setShowAddToGroupDialog] = useState(false);
  const [isAddingToGroup, setIsAddingToGroup] = useState(false);

  const { config } = useConfig();
  const startTriageMutation = useStartTriage();

  // Fetch existing groups for "Add to Group" functionality
  const { data: groupsData } = useAlertGroups({
    page: 1,
    page_size: 100, // Get all groups for selection
  });

  const getTimeRangeParam = (timeRange: TimeRange): string | null => {
    switch (timeRange) {
      case '30m': return '30m';
      case '1h': return '1h';
      case '24h': return '24h';
      case '7d': return '7d';
      case '30d': return '30d';
      case 'custom': return 'custom';
      default: return '30d';
    }
  };

  const queryParams: AlertsQueryParams = useMemo(() => {
    const params: AlertsQueryParams = {
      page: currentPage,
      page_size: itemsPerPage,
      time_range: getTimeRangeParam(timeRange),
    };

    if (timeRange === 'custom' && customTimeRange) {
      params.start_time = customTimeRange.start.toISOString();
      params.end_time = customTimeRange.end.toISOString();
    }

    if (searchTerm.trim()) {
      params.name_contains = searchTerm.trim();
    }

    if (severityFilter !== "all") {
      params.severity = severityFilter;
    }

    if (triageStatusFilter !== "all") {
      params.triage_status = triageStatusFilter;
    }

    if (scoreRange !== "all") {
      // When filtering by score, we only show alerts with successful evaluations
      params.evaluation_status = "success";

      switch (scoreRange) {
        case "excellent":
          params.evaluation_score_operator = ">";
          params.evaluation_score_value = 90.0;
          break;
        case "good":
          params.evaluation_score_operator = ">=";
          params.evaluation_score_value = 70.0;
          break;
        case "average":
          params.evaluation_score_operator = ">=";
          params.evaluation_score_value = 50.0;
          break;
        case "poor":
          params.evaluation_score_operator = "<";
          params.evaluation_score_value = 50.0;
          break;
      }
    }

    return params;
  }, [currentPage, itemsPerPage, timeRange, customTimeRange, searchTerm, severityFilter, triageStatusFilter, scoreRange]);

  const { data: alertsResponse, isLoading, error, refetch } = useUngroupedAlerts(queryParams);

  const alerts = alertsResponse?.alerts || [];
  const pagination = alertsResponse?.pagination;
  const totalItems = pagination?.total_items || 0;
  const totalPages = Math.ceil(totalItems / itemsPerPage);

  const handleFilterChange = () => {
    setCurrentPage(1);
  };

  const handleRowClick = (alert: AlertType) => {
    onAlertClick?.(alert);
  };

  const handleManualTriage = async (alertId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    setTriggeringTriage(alertId);
    try {
      await startTriageMutation.mutateAsync(alertId);
      await refetch();
      toast.success("Manual triage started successfully");
    } catch (error: any) {
      console.error("Failed to start manual triage:", error);
      toast.error(error?.response?.data?.detail || "Failed to start manual triage");
    } finally {
      setTriggeringTriage(null);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const datePart = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const timePart = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    return `${datePart} at ${timePart}`;
  };

  const handleSelectAlert = (alertId: string) => {
    setSelectedAlerts(prev => {
      const newSet = new Set(prev);
      if (newSet.has(alertId)) {
        newSet.delete(alertId);
      } else {
        newSet.add(alertId);
      }
      return newSet;
    });
  };

  const handleSelectAll = () => {
    if (selectedAlerts.size === alerts.length) {
      setSelectedAlerts(new Set());
    } else {
      setSelectedAlerts(new Set(alerts.map(a => a.id)));
    }
  };

  const handleCreateGroup = async (groupName: string, description: string) => {
    if (selectedAlerts.size === 0) {
      toast.error("Please select at least one alert");
      return;
    }

    if (!groupName.trim()) {
      toast.error("Please enter a group name");
      return;
    }

    // Check if only 1 alert is selected
    if (selectedAlerts.size < 2) {
      toast.error("Please select at least 2 alerts to create a group");
      return;
    }

    setIsCreatingGroup(true);
    try {
      await apiClient.post("/alerts/create-manual-group", {
        alert_ids: Array.from(selectedAlerts),
        group_name: groupName.trim(),
        description: description?.trim() || undefined
      });

      toast.success(`Group "${groupName}" created successfully with ${selectedAlerts.size} alerts`);
      setSelectedAlerts(new Set());
      setShowCreateDialog(false);
      setCurrentPage(1); // Reset to page 1
      await refetch(); // Refetch ungrouped alerts
    } catch (error: any) {
      console.error("Failed to create group:", error);
      toast.error(error?.response?.data?.detail || "Failed to create group");
    } finally {
      setIsCreatingGroup(false);
    }
  };

  const handleAddToGroup = async (groupId: string) => {
    setIsAddingToGroup(true);
    try {
      await apiClient.post(`/alert-groups/${groupId}/alerts`, {
        alert_ids: Array.from(selectedAlerts)
      });

      toast.success(`${selectedAlerts.size} alert(s) added to group successfully`);
      setSelectedAlerts(new Set());
      setShowAddToGroupDialog(false);
      setCurrentPage(1);
      await refetch();
    } catch (error: any) {
      console.error("Failed to add alerts to group:", error);
      toast.error(error?.response?.data?.detail || "Failed to add alerts to group");
    } finally {
      setIsAddingToGroup(false);
    }
  };

  if (error) {
    return (
      <div className="flex justify-center w-full">
        <Card className="border border-border p-6 box-shadow w-full">
          <div className="flex flex-col items-center justify-center py-16 px-4">
            <AlertCircle className="h-12 w-12 text-danger" />
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">Failed to load ungrouped alerts</h3>
              <p className="text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'Failed to load ungrouped alerts'}
              </p>
              <Button onClick={() => refetch()} variant="outline">
                Try Again
              </Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  const hasNoData = alerts.length === 0;

  return (
    <TooltipProvider>
      <div className="space-y-4">
        {/* Selection Actions Card */}
        {selectedAlerts.size > 0 && (
          <Card className="p-4 bg-primary/5 border-primary/20" style={{ boxShadow: "0px 4px 6px 0px #0000000D"}}>
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 flex-1">
                <Layers className="h-5 w-5 text-primary" />
                <div>
                  <div className="font-medium text-foreground">
                    {selectedAlerts.size} alert{selectedAlerts.size !== 1 ? 's' : ''} selected
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {selectedAlerts.size === 1
                      ? "You can add this alert to an existing group or select 2+ alerts to create a new group"
                      : "Choose an action for the selected alerts"
                    }
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  onClick={() => setShowAddToGroupDialog(true)}
                  className="h-10"
                >
                  <Layers className="mr-2 h-4 w-4" />
                  Add to Existing Group
                </Button>
                <Button
                  onClick={() => {
                    if (selectedAlerts.size < 2) {
                      toast.error("Please select at least 2 alerts to create a group");
                      return;
                    }
                    setShowCreateDialog(true);
                  }}
                  disabled={selectedAlerts.size < 2}
                  className="h-10 bg-primary hover:bg-primary/90"
                >
                  <Layers className="mr-2 h-4 w-4" />
                  Create New Group
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setSelectedAlerts(new Set())}
                  className="h-10"
                >
                  Clear
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* Search and Filters Card */}
        <Card className="p-4" style={{ boxShadow: "0px 4px 6px 0px #0000000D"}}>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 flex-1">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                <Input
                  placeholder="Search by name or ID..."
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    handleFilterChange();
                  }}
                  className="pl-10 h-10"
                />
              </div>

              <div className="text-sm text-muted-foreground whitespace-nowrap">
                {totalItems} alert{totalItems !== 1 ? 's' : ''}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Select
                value={severityFilter}
                onValueChange={(value: SeverityType | "all") => {
                  setSeverityFilter(value);
                  handleFilterChange();
                }}
              >
                <SelectTrigger className="w-36 h-10">
                  <SelectValue placeholder="All Severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severity</SelectItem>
                  <SelectItem value="P1">P1 - Critical</SelectItem>
                  <SelectItem value="P2">P2 - High</SelectItem>
                  <SelectItem value="P3">P3 - Medium</SelectItem>
                </SelectContent>
              </Select>

              <Select
                value={triageStatusFilter}
                onValueChange={(value: StatusType | "all") => {
                  setTriageStatusFilter(value);
                  handleFilterChange();
                }}
              >
                <SelectTrigger className="w-36 h-10">
                  <SelectValue placeholder="All Triage" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Triage</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="processing">Processing</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                  <SelectItem value="queued">Queued</SelectItem>
                </SelectContent>
              </Select>

              <Select
                value={scoreRange}
                onValueChange={(value: string) => {
                  setScoreRange(value);
                  handleFilterChange();
                }}
              >
                <SelectTrigger className="w-36 h-10">
                  <SelectValue placeholder="All Scores" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Scores</SelectItem>
                  <SelectItem value="excellent">Excellent (&gt;90%)</SelectItem>
                  <SelectItem value="good">Good (≥70%)</SelectItem>
                  <SelectItem value="average">Average (≥50%)</SelectItem>
                  <SelectItem value="poor">Poor (&lt;50%)</SelectItem>
                </SelectContent>
              </Select>

              <Select
                value={itemsPerPage.toString()}
                onValueChange={(value: string) => {
                  setItemsPerPage(parseInt(value));
                  handleFilterChange();
                }}
              >
                <SelectTrigger className="w-36 h-10">
                  <SelectValue placeholder="Items per page" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">5 per page</SelectItem>
                  <SelectItem value="10">10 per page</SelectItem>
                  <SelectItem value="25">25 per page</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Card>

        {/* Table */}
        {isLoading ? (
          <Card className="flex items-center justify-center py-16" style={{ boxShadow: "0px 4px 6px 0px #0000000D"}}>
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </Card>
        ) : hasNoData ? (
          <Card className="p-6" style={{ boxShadow: "0px 4px 6px 0px #0000000D"}}>
            <div className="flex flex-col items-center justify-center py-16 px-4">
              <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">No ungrouped alerts found</h3>
              <p className="text-sm text-muted-foreground text-center max-w-md">
                All alerts have been grouped or no alerts match your current filters
              </p>
            </div>
          </Card>
        ) : (
          <Card style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      checked={selectedAlerts.size === alerts.length && alerts.length > 0}
                      onCheckedChange={handleSelectAll}
                      aria-label="Select all alerts"
                    />
                  </TableHead>
                  <TableHead className="table-header-text w-16">ID</TableHead>
                  <TableHead className="table-header-text">ALERT NAME</TableHead>
                  <TableHead className="table-header-text text-center w-32">SEVERITY</TableHead>
                  <TableHead className="table-header-text text-center w-32">STATUS</TableHead>
                  <TableHead className="table-header-text text-center w-24">SCORE</TableHead>
                  <TableHead className="table-header-text w-40">STARTED</TableHead>
                  <TableHead className="table-header-text w-40">LAST UPDATE</TableHead>
                  {config && !config.automatic_triage && <TableHead className="table-header-text w-24 text-center">ACTIONS</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => (
                  <TableRow
                    key={alert.id}
                    className={cn(
                      "cursor-pointer hover:bg-muted/50 transition-colors",
                      selectedAlerts.has(alert.id) && "bg-primary/5"
                    )}
                    onClick={() => handleRowClick(alert)}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedAlerts.has(alert.id)}
                        onCheckedChange={() => handleSelectAlert(alert.id)}
                        aria-label={`Select alert ${alert.id}`}
                      />
                    </TableCell>
                    <TableCell className="font-medium">{alert.id}</TableCell>
                    <TableCell className="font-normal max-w-md truncate">{alert.name}</TableCell>
                    <TableCell className="text-center">
                      <SeverityChip severity={alert.severity} />
                    </TableCell>
                    <TableCell className="text-center">
                      <StatusChip status={alert.triage_status} />
                    </TableCell>
                    <TableCell className="text-center">
                      {alert.evaluation_score !== null && alert.evaluation_score !== undefined ? (
                        <span className="text-sm font-medium">{alert.evaluation_score}%</span>
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(alert.started_at)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(alert.last_updated_at)}</TableCell>
                    {config && !config.automatic_triage && (
                      <TableCell className="text-center">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={(e) => handleManualTriage(alert.id, e)}
                              disabled={triggeringTriage === alert.id}
                              className="h-8 w-8 p-0"
                            >
                              {triggeringTriage === alert.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Play className="h-4 w-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Start Manual Triage</TooltipContent>
                        </Tooltip>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}

        {/* Pagination */}
        {!hasNoData && totalPages > 1 && (
          <div className="flex justify-between items-center px-6 py-4 bg-muted border-t" style={{ marginTop: -21 }}>
            <div className="text-sm">
              <span className="text-muted-foreground">Showing</span>{" "}
              <span className="font-bold">
                {Math.min((currentPage - 1) * itemsPerPage + 1, totalItems)}-
                {Math.min(currentPage * itemsPerPage, totalItems)}
              </span>{" "}
              of <span className="font-bold">{totalItems}</span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className="table-pg-button text-muted-foreground"
              >
                Previous
              </Button>

              <div className="flex items-center gap-2">
                {(() => {
                  const pages = [];
                  const delta = 2; // Number of pages to show around current page

                  // Always show first page
                  pages.push(
                    <Button
                      key={1}
                      variant={currentPage === 1 ? "default" : "outline"}
                      onClick={() => setCurrentPage(1)}
                      className={cn(
                        "table-pg-number-btn text-muted-foreground",
                        currentPage === 1
                          ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                          : "hover:bg-muted"
                      )}
                    >
                      1
                    </Button>
                  );

                  // Show ellipsis if there's a gap after first page
                  if (currentPage > delta + 2) {
                    pages.push(
                      <span key="ellipsis-start" className="px-2 text-muted-foreground">
                        ...
                      </span>
                    );
                  }

                  // Show pages around current page
                  const startPage = Math.max(2, currentPage - delta);
                  const endPage = Math.min(totalPages - 1, currentPage + delta);

                  for (let i = startPage; i <= endPage; i++) {
                    pages.push(
                      <Button
                        key={i}
                        variant={currentPage === i ? "default" : "outline"}
                        onClick={() => setCurrentPage(i)}
                        className={cn(
                          "table-pg-number-btn text-muted-foreground",
                          currentPage === i
                            ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                            : "hover:bg-muted"
                        )}
                      >
                        {i}
                      </Button>
                    );
                  }

                  // Show ellipsis if there's a gap before last page
                  if (currentPage < totalPages - delta - 1) {
                    pages.push(
                      <span key="ellipsis-end" className="px-2 text-muted-foreground">
                        ...
                      </span>
                    );
                  }

                  // Last page (if not already shown)
                  if (totalPages > 1) {
                    pages.push(
                      <Button
                        key={totalPages}
                        variant={currentPage === totalPages ? "default" : "outline"}
                        onClick={() => setCurrentPage(totalPages)}
                        className={cn(
                          "table-pg-number-btn text-muted-foreground",
                          currentPage === totalPages
                            ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                            : "hover:bg-muted"
                        )}
                      >
                        {totalPages}
                      </Button>
                    );
                  }

                  return pages;
                })()}
              </div>

              <Button
                variant="outline"
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className="table-pg-button text-muted-foreground"
              >
                Next
              </Button>
            </div>
          </div>
        )}

        {/* Create Group Dialog */}
        <CreateGroupDialog
          open={showCreateDialog}
          onOpenChange={setShowCreateDialog}
          selectedAlerts={alerts.filter(a => selectedAlerts.has(a.id)).map(a => ({ id: a.id, name: a.name }))}
          onCreateGroup={handleCreateGroup}
          isCreating={isCreatingGroup}
        />

        {/* Add to Group Dialog */}
        <AddToGroupDialog
          open={showAddToGroupDialog}
          onOpenChange={setShowAddToGroupDialog}
          selectedAlerts={alerts.filter(a => selectedAlerts.has(a.id)).map(a => ({ id: a.id, name: a.name }))}
          existingGroups={groupsData?.groups || []}
          onAddToGroup={handleAddToGroup}
          isAdding={isAddingToGroup}
        />
      </div>
    </TooltipProvider>
  );
}
