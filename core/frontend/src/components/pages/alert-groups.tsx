import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { TimeRangeSelector, TimeRange } from "../time-range-selector";
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
import { Search, Loader2, RefreshCw, Layers } from "lucide-react";
import { cn } from "../ui/utils";
import { Badge } from "../ui/badge";

// Mock data - Replace with actual API hook later
const mockAlertGroups = [
  {
    id: 15,
    name: "Database Connection Timeout",
    alert_count: 8,
    severity: "P2" as SeverityType,
    triage_status: "success" as StatusType,
    status: "active",
    confidence: 92,
    created_at: "2 hours ago",
    updated_at: "5 minutes ago"
  },
  {
    id: 14,
    name: "API Gateway Errors",
    alert_count: 12,
    severity: "P1" as SeverityType,
    triage_status: "processing" as StatusType,
    status: "active",
    confidence: 87,
    created_at: "1 hour ago",
    updated_at: "10 minutes ago"
  },
  {
    id: 13,
    name: "Memory Leak Pattern",
    alert_count: 5,
    severity: "P2" as SeverityType,
    triage_status: "pending" as StatusType,
    status: "active",
    confidence: 78,
    created_at: "3 hours ago",
    updated_at: "1 hour ago"
  },
  {
    id: 12,
    name: "Network Latency Issues",
    alert_count: 3,
    severity: "P3" as SeverityType,
    triage_status: "success" as StatusType,
    status: "active",
    confidence: 95,
    created_at: "4 hours ago",
    updated_at: "2 hours ago"
  },
  {
    id: 11,
    name: "Cache Invalidation",
    alert_count: 20,
    severity: "P1" as SeverityType,
    triage_status: "success" as StatusType,
    status: "resolved",
    confidence: 88,
    created_at: "6 hours ago",
    updated_at: "3 hours ago"
  }
];

interface AlertGroupsProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange, customRange?: { start: Date; end: Date }) => void;
  customTimeRange?: { start: Date; end: Date };
}

export function AlertGroups({ timeRange, onTimeRangeChange, customTimeRange }: AlertGroupsProps) {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityType | "all">("all");
  const [triageStatusFilter, setTriageStatusFilter] = useState<StatusType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [isLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);

  // Filter data
  const filteredGroups = useMemo(() => {
    return mockAlertGroups.filter(group => {
      if (searchTerm && !group.name.toLowerCase().includes(searchTerm.toLowerCase())) {
        return false;
      }
      if (severityFilter !== "all" && group.severity !== severityFilter) {
        return false;
      }
      if (triageStatusFilter !== "all" && group.triage_status !== triageStatusFilter) {
        return false;
      }
      if (statusFilter !== "all" && group.status !== statusFilter) {
        return false;
      }
      return true;
    });
  }, [searchTerm, severityFilter, triageStatusFilter, statusFilter]);

  const totalItems = filteredGroups.length;
  const hasNoData = totalItems === 0 && !searchTerm && severityFilter === "all" && triageStatusFilter === "all";

  const handleRefresh = () => {
    setIsFetching(true);
    // Simulate refresh
    setTimeout(() => setIsFetching(false), 1000);
  };

  const handleFilterChange = () => {
    setCurrentPage(1);
  };

  const handleRowClick = (groupId: number) => {
    navigate(`/alert-groups/${groupId}`);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title font-bold title-lg-header">Alert Groups</h1>
          <p className="text-secondary">Grouped alerts with correlated root causes</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={handleRefresh}
            disabled={isFetching}
            className="flex items-center gap-1.5 bg-card text-sm font-medium transition-colors border border-border-medium text-muted-foreground"
            style={{ padding: "18px 22px" }}
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <TimeRangeSelector
            value={timeRange}
            onChange={onTimeRangeChange}
            customRange={customTimeRange}
          />
        </div>
      </div>

      {/* Filter Bar */}
      <Card className="p-4" style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
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
              {totalItems} group{totalItems !== 1 ? 's' : ''} found
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

      {/* Loading State */}
      {isLoading || isFetching ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-loading" />
        </div>
      ) : hasNoData ? (
        /* Empty State */
        <div className="flex items-center justify-center py-16 px-4">
          <div className="text-center max-w-md">
            <div className="mb-4">
              <div className="mx-auto w-16 h-16 bg-surface-secondary rounded-full flex items-center justify-center">
                <Layers className="h-8 w-8 text-muted" />
              </div>
            </div>
            <h3 className="text-lg font-medium text-foreground mb-2">No Alert Groups Available</h3>
            <p className="text-secondary">
              There are no alert groups in the selected time range.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* Alert Groups Table */}
          <Card style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">ID</TableHead>
                  <TableHead>Group Name</TableHead>
                  <TableHead className="text-center w-24">Alerts</TableHead>
                  <TableHead className="text-center w-32">Severity</TableHead>
                  <TableHead className="text-center w-32">Triage Status</TableHead>
                  <TableHead className="text-center w-24">Status</TableHead>
                  <TableHead className="w-32">Confidence</TableHead>
                  <TableHead className="w-32">Created</TableHead>
                  <TableHead className="w-32">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredGroups.map((group) => (
                  <TableRow
                    key={group.id}
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => handleRowClick(group.id)}
                  >
                    <TableCell className="font-medium">{group.id}</TableCell>
                    <TableCell className="font-medium">{group.name}</TableCell>
                    <TableCell className="text-center">
                      <Badge variant="secondary" className="bg-surface-secondary text-secondary">
                        {group.alert_count}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <SeverityChip severity={group.severity} />
                    </TableCell>
                    <TableCell className="text-center">
                      <StatusChip status={group.triage_status} />
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant={group.status === "active" ? "default" : "secondary"}
                        className={cn(
                          "capitalize",
                          group.status === "active" && "bg-green-200 text-green-500 border-green-500"
                        )}
                      >
                        {group.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{group.confidence}%</span>
                        <div className="flex-1 h-1.5 bg-surface-secondary rounded-full overflow-hidden max-w-[60px]">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all",
                              group.confidence >= 90 ? "bg-score-high" :
                              group.confidence >= 70 ? "bg-yellow-500" :
                              "bg-score-low"
                            )}
                            style={{ width: `${group.confidence}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-secondary">{group.created_at}</TableCell>
                    <TableCell className="text-sm text-secondary">{group.updated_at}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}

