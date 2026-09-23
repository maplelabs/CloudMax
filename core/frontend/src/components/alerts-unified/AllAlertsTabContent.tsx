import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../ui/card";
import { Alert as AlertType, StatusType } from "../../types/alerts";
import { TimeRange } from "../time-range-selector";
import { useAllAlerts } from "../../hooks/useAllAlerts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { SeverityChip, SeverityType } from "../severity-chip";
import { StatusChip } from "../status-chip";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { AlertCircle, Loader2, Search, Play } from "lucide-react";
import { cn } from "../ui/utils";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "../ui/tooltip";
import { useStartTriage } from "../../hooks/useAlerts";
import { toast } from "sonner";
import { useConfig } from "../../hooks/useConfig";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

interface AllAlertsTabContentProps {
  timeRange: TimeRange;
  customTimeRange?: { start: Date; end: Date };
  onAlertClick?: (alert: AlertType) => void;
}

export function AllAlertsTabContent({
  timeRange,
  customTimeRange,
  onAlertClick
}: AllAlertsTabContentProps) {
  const navigate = useNavigate();
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [triggeringTriage, setTriggeringTriage] = useState<string | null>(null);

  // Filter states
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [triageStatusFilter, setTriageStatusFilter] = useState<string>("all");
  const [scoreFilter, setScoreFilter] = useState<string>("all");

  const { data: config } = useConfig();
  const startTriageMutation = useStartTriage();

  // Build query parameters
  const queryParams: any = {
    page: currentPage,
    page_size: pageSize,
  };

  // Add search filter
  if (searchTerm.trim()) {
    queryParams.name_contains = searchTerm.trim();
  }

  // Add filters
  if (severityFilter !== "all") queryParams.severity = severityFilter;
  if (triageStatusFilter !== "all") queryParams.triage_status = triageStatusFilter;

  // Handle score range filtering (matching reference.jsx logic)
  if (scoreFilter !== "all") {
    // When filtering by score, we only show alerts with successful evaluations
    queryParams.evaluation_status = "success";

    switch (scoreFilter) {
      case "excellent":
        queryParams.evaluation_score_operator = ">";
        queryParams.evaluation_score_value = 90.0;
        break;
      case "good":
        queryParams.evaluation_score_operator = ">=";
        queryParams.evaluation_score_value = 70.0;
        break;
      case "average":
        queryParams.evaluation_score_operator = ">=";
        queryParams.evaluation_score_value = 50.0;
        break;
      case "poor":
        queryParams.evaluation_score_operator = "<";
        queryParams.evaluation_score_value = 50.0;
        break;
    }
  }

  // Add time range
  if (timeRange === "custom" && customTimeRange) {
    queryParams.time_range = "custom";
    queryParams.start_time = customTimeRange.start.toISOString();
    queryParams.end_time = customTimeRange.end.toISOString();
  } else if (timeRange !== "all") {
    queryParams.time_range = timeRange;
  }

  const { data, isLoading, error, refetch } = useAllAlerts(queryParams);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, severityFilter, triageStatusFilter, scoreFilter, timeRange, pageSize]);

  const handleAlertClick = (alert: AlertType) => {
    if (onAlertClick) {
      onAlertClick(alert);
    } else {
      navigate(`/alerts/${alert.id}`);
    }
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const datePart = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const timePart = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    return `${datePart} at ${timePart}`;
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

  if (error) {
    return (
      <div className="flex justify-center w-full">
        <Card className="border border-border p-6 box-shadow w-full">
          <div className="flex flex-col items-center justify-center py-16 px-4">
            <AlertCircle className="h-12 w-12 text-danger" />
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">Failed to load alerts</h3>
              <p className="text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'Failed to load alerts'}
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

  const totalAlerts = data?.pagination?.total_items || 0;

  return (
    <TooltipProvider>
    <div className="space-y-4">
      {/* Search and Filters Card */}
      <Card className="p-4" style={{ boxShadow: "0px 4px 6px 0px #0000000D"}}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input
                placeholder="Search alerts..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-10"
              />
            </div>

            <div className="text-sm text-muted-foreground whitespace-nowrap">
              {totalAlerts} alert{totalAlerts !== 1 ? 's' : ''}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Select
              value={severityFilter}
              onValueChange={setSeverityFilter}
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
              onValueChange={setTriageStatusFilter}
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
              value={scoreFilter}
              onValueChange={setScoreFilter}
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
              value={pageSize.toString()}
              onValueChange={(value) => setPageSize(parseInt(value))}
            >
              <SelectTrigger className="w-36 h-10">
                <SelectValue />
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

      {/* Table Card */}
      <Card style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
        <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="table-header-text w-20">ID</TableHead>
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
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                    <p className="mt-2 text-sm text-muted-foreground">Loading alerts...</p>
                  </TableCell>
                </TableRow>
              ) : !data?.alerts || data.alerts.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12">
                    <AlertCircle className="h-8 w-8 mx-auto text-muted-foreground" />
                    <p className="mt-2 text-sm text-muted-foreground">
                      No alerts found matching the selected filters
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                data.alerts.map((alert) => (
                  <TableRow
                    key={alert.id}
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => handleAlertClick(alert)}
                  >
                    <TableCell className="font-medium">{alert.id}</TableCell>
                    <TableCell>
                      <div className="font-normal">{alert.name}</div>
                    </TableCell>
                    <TableCell className="text-center">
                      <div className="flex justify-center">
                        <SeverityChip severity={alert.severity as SeverityType} />
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <div className="flex justify-center">
                        <StatusChip status={alert.triage_status as StatusType} />
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      {alert.evaluation_score !== undefined && alert.evaluation_score !== null ? (
                        <span className="text-sm font-medium">{alert.evaluation_score}%</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(alert.started_at)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {alert.last_updated_at
                        ? formatDate(alert.last_updated_at)
                        : formatDate(alert.started_at)
                      }
                    </TableCell>
                    {config && !config.automatic_triage && (
                      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
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
                ))
              )}
            </TableBody>
          </Table>

        {/* Pagination */}
        {data?.pagination && data.pagination.total_items > 0 && (
          <div className="flex justify-between items-center px-6 py-4 bg-muted border-t" style={{ marginTop: -21 }}>
            <div className="text-sm">
              <span className="text-muted-foreground">Showing</span>{" "}
              <span className="font-bold">
                {Math.min((data.pagination.current_page - 1) * pageSize + 1, data.pagination.total_items)}-
                {Math.min(data.pagination.current_page * pageSize, data.pagination.total_items)}
              </span>{" "}
              of <span className="font-bold">{data.pagination.total_items}</span>
            </div>

            {Math.ceil(data.pagination.total_items / data.pagination.page_size) > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  onClick={() => handlePageChange(Math.max(1, data.pagination.current_page - 1))}
                  disabled={data.pagination.current_page === 1}
                  className="table-pg-button text-muted-foreground"
                >
                  Previous
                </Button>

                <div className="flex items-center gap-2">
                  {(() => {
                    const totalPages = Math.ceil(data.pagination.total_items / data.pagination.page_size);
                    const currentPage = data.pagination.current_page;
                    const pages = [];
                    const delta = 2;

                    // First page
                    pages.push(
                      <Button
                        key={1}
                        variant={currentPage === 1 ? "default" : "outline"}
                        onClick={() => handlePageChange(1)}
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

                    // Ellipsis after first page
                    if (currentPage > delta + 2) {
                      pages.push(
                        <span key="ellipsis-start" className="px-2 text-muted-foreground">
                          ...
                        </span>
                      );
                    }

                    // Pages around current page
                    const startPage = Math.max(2, currentPage - delta);
                    const endPage = Math.min(totalPages - 1, currentPage + delta);

                    for (let i = startPage; i <= endPage; i++) {
                      pages.push(
                        <Button
                          key={i}
                          variant={currentPage === i ? "default" : "outline"}
                          onClick={() => handlePageChange(i)}
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

                    // Ellipsis before last page
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
                          onClick={() => handlePageChange(totalPages)}
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
                  onClick={() => handlePageChange(Math.min(Math.ceil(data.pagination.total_items / data.pagination.page_size), data.pagination.current_page + 1))}
                  disabled={data.pagination.current_page === Math.ceil(data.pagination.total_items / data.pagination.page_size)}
                  className="table-pg-button text-muted-foreground"
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
    </TooltipProvider>
  );
}
