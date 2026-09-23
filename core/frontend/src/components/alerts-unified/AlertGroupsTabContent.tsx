import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { TimeRange } from "../time-range-selector";
import { StatusChip, StatusType } from "../status-chip";
import { SeverityChip, SeverityType } from "../severity-chip";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "../ui/table";
import { Card } from "../ui/card";
import { Search, Loader2, AlertCircle, Layers, Play } from "lucide-react";
import { cn } from "../ui/utils";
import { useAlertGroups, AlertGroup } from "../../hooks/useAlertGroups";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { toast } from "sonner";
import { useConfig } from "../../hooks/useConfig";
import apiClient from "../../service/api";

interface AlertGroupsTabContentProps {
  timeRange: TimeRange;
  customTimeRange?: { start: Date; end: Date };
  onGroupClick?: (groupId: string) => void;
}

export function AlertGroupsTabContent({
  timeRange,
  customTimeRange,
  onGroupClick
}: AlertGroupsTabContentProps) {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityType | "all">("all");
  const [triageStatusFilter, setTriageStatusFilter] = useState<StatusType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [scoreRange] = useState<string>("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [triggeringTriage, setTriggeringTriage] = useState<string | null>(null);

  const { data: config } = useConfig();

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

  const queryParams: any = useMemo(() => {
    const params: any = {
      page: currentPage,
      page_size: itemsPerPage,
    };

    if (searchTerm) params.name_contains = searchTerm;
    if (severityFilter !== "all") params.severity = severityFilter;
    if (triageStatusFilter !== "all") params.triage_status = triageStatusFilter;
    if (statusFilter !== "all") params.status = statusFilter;

    const time_range = getTimeRangeParam(timeRange);
    if (time_range) {
      params.time_range = time_range;
    }

    if (time_range === 'custom' && customTimeRange) {
      params.start_time = customTimeRange.start.toISOString();
      params.end_time = customTimeRange.end.toISOString();
    }

    if (scoreRange !== "all") {
      const [operator, value] = scoreRange.split(":");
      if (operator && value) {
        params.evaluation_score_operator = operator;
        params.evaluation_score_value = parseFloat(value);
      }
    }

    return params;
  }, [currentPage, itemsPerPage, searchTerm, severityFilter, triageStatusFilter, statusFilter, timeRange, customTimeRange, scoreRange]);

  const { data: groupsData, isLoading, error, refetch } = useAlertGroups(queryParams);

  const groups = groupsData?.groups || [];
  const pagination = groupsData?.pagination;
  const totalItems = pagination?.total_items || 0;
  const totalPages = Math.ceil(totalItems / itemsPerPage);

  const handleFilterChange = () => {
    setCurrentPage(1);
  };

  const handleRowClick = (groupId: string) => {
    if (onGroupClick) {
      onGroupClick(groupId);
    } else {
      navigate(`/alert-groups/${groupId}`);
    }
  };

  const handleManualTriage = async (groupId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    setTriggeringTriage(groupId);
    try {
      await apiClient.post(`/alert-groups/${groupId}/triage`);
      await refetch();
      toast.success("Manual group triage started successfully");
    } catch (error: any) {
      console.error("Failed to start manual group triage:", error);
      toast.error(error?.response?.data?.detail || "Failed to start manual group triage");
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

  if (error) {
    return (
      <div className="flex justify-center w-full">
        <Card className="border border-border p-6 box-shadow w-full">
          <div className="flex flex-col items-center justify-center py-16 px-4">
            <AlertCircle className="h-12 w-12 text-danger" />
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">Failed to load alert groups</h3>
              <p className="text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'Failed to load alert groups'}
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

  const hasNoData = groups.length === 0;

  return (
    <div className="space-y-4">
      {/* Search and Filters Card */}
      <Card className="p-4" style={{ boxShadow: "0px 4px 6px 0px #0000000D"}}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input
                placeholder="Search groups..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  handleFilterChange();
                }}
                className="pl-10 h-10"
              />
            </div>

            <div className="text-sm text-muted-foreground whitespace-nowrap">
              {totalItems} group{totalItems !== 1 ? 's' : ''}
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
              value={statusFilter}
              onValueChange={(value: string) => {
                setStatusFilter(value);
                handleFilterChange();
              }}
            >
              <SelectTrigger className="w-36 h-10">
                <SelectValue placeholder="All Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="resolved">Resolved</SelectItem>
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
            <Layers className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">No alert groups found</h3>
            <p className="text-sm text-muted-foreground text-center max-w-md">
              No alert groups match your current filters
            </p>
          </div>
        </Card>
      ) : (
        <Card style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="table-header-text w-16">ID</TableHead>
                <TableHead className="table-header-text">GROUP NAME</TableHead>
                <TableHead className="table-header-text text-center w-24">ALERTS</TableHead>
                <TableHead className="table-header-text text-center w-32">SEVERITY</TableHead>
                <TableHead className="table-header-text text-center w-32">STATUS</TableHead>
                <TableHead className="table-header-text text-center w-24">SCORE</TableHead>
                <TableHead className="table-header-text w-32">CREATED</TableHead>
                <TableHead className="table-header-text w-32">LAST UPDATE</TableHead>
                {config && !config.automatic_triage && (
                  <TableHead className="table-header-text text-center w-20">ACTIONS</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((group: AlertGroup) => (
                <TableRow
                  key={group.id}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => handleRowClick(group.id)}
                >
                  <TableCell className="font-medium">{group.id}</TableCell>
                  <TableCell className="font-normal max-w-md truncate">{group.group_name}</TableCell>
                  <TableCell className="text-center">
                    <div className="flex justify-center">
                      <span
                        className="inline-flex items-center justify-center w-8 h-6 rounded-full text-white text-sm font-medium"
                        style={{ backgroundColor: '#323a46' }}
                      >
                        {group.alert_count}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-center">
                    <SeverityChip severity={group.severity} />
                  </TableCell>
                  <TableCell className="text-center">
                    <StatusChip status={group.triage_status as StatusType} />
                  </TableCell>
                  <TableCell className="text-center">
                    {group.evaluation_score !== null && group.evaluation_score !== undefined ? (
                      <span className="text-sm font-medium">{group.evaluation_score}%</span>
                    ) : (
                      <span className="text-sm text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(group.created_at)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(group.updated_at)}
                  </TableCell>
                  {config && !config.automatic_triage && (
                    <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => handleManualTriage(group.id, e)}
                            disabled={triggeringTriage === group.id}
                            className="h-8 w-8 p-0"
                          >
                            {triggeringTriage === group.id ? (
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
                const delta = 2;

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

                if (currentPage > delta + 2) {
                  pages.push(<span key="ellipsis1" className="px-2">...</span>);
                }

                for (let i = Math.max(2, currentPage - delta); i <= Math.min(totalPages - 1, currentPage + delta); i++) {
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

                if (currentPage < totalPages - delta - 1) {
                  pages.push(<span key="ellipsis2" className="px-2">...</span>);
                }

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
    </div>
  );
}
