import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { TimeRangeSelector, TimeRange } from "../time-range-selector";
import { Button } from "../ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { RefreshCw, Layers, AlertCircle, List, Plus } from "lucide-react";
import { Alert as AlertType } from "../../types/alerts";
import { toast } from "sonner";
import { AlertsTabContent } from "../alerts-unified/AlertsTabContent";
import { AlertGroupsTabContent } from "../alerts-unified/AlertGroupsTabContent";
import { AllAlertsTabContent } from "../alerts-unified/AllAlertsTabContent";
import { CreateAlertDialog } from "../alerts-unified/CreateAlertDialog";
import { useUngroupedAlerts } from "../../hooks/useUngroupedAlerts";
import { useAlertGroups } from "../../hooks/useAlertGroups";
import { useAllAlerts } from "../../hooks/useAllAlerts";

interface AlertsUnifiedProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange, customRange?: { start: Date; end: Date }) => void;
  customTimeRange?: { start: Date; end: Date };
  onAlertClick?: (alert: AlertType) => void;
  onGroupClick?: (groupId: number) => void;
}

// Tab configuration
const TAB_CONFIG = [
  { value: "groups", label: "Alert Groups", icon: Layers },
  { value: "ungrouped", label: "Ungrouped Alerts", icon: AlertCircle },
  { value: "all", label: "All Alerts", icon: List },
] as const;

type TabValue = typeof TAB_CONFIG[number]["value"];

export function AlertsUnified({
  timeRange,
  onTimeRangeChange,
  customTimeRange,
  onAlertClick,
  onGroupClick
}: AlertsUnifiedProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as TabValue | null;

  // Simplified: Use URL param directly or default to "groups"
  const [activeTab, setActiveTab] = useState<string>(tabParam || "groups");

  // Create Alert Dialog state
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);

  // Sync with URL parameter changes
  useEffect(() => {
    if (tabParam && tabParam !== activeTab) {
      setActiveTab(tabParam);
    }
  }, [tabParam, activeTab]);

  // Helper to get time range param
  const getTimeRangeParam = () => timeRange === 'custom' ? 'custom' : timeRange;

  // Build query params for tab counts
  const tabQueryParams: any = {
    page: 1,
    page_size: 1,
    time_range: getTimeRangeParam()
  };

  // Add custom time range if applicable
  if (timeRange === 'custom' && customTimeRange) {
    tabQueryParams.start_time = customTimeRange.start.toISOString();
    tabQueryParams.end_time = customTimeRange.end.toISOString();
  }

  // Fetch counts for all tabs with time range filter
  const { data: ungroupedData } = useUngroupedAlerts(tabQueryParams);

  const { data: groupsData } = useAlertGroups(tabQueryParams);

  const { data: allAlertsData } = useAllAlerts(tabQueryParams);

  // Map counts by tab value
  const tabCounts: Record<TabValue, number> = {
    groups: groupsData?.pagination?.total_items || 0,
    ungrouped: ungroupedData?.pagination?.total_items || 0,
    all: allAlertsData?.pagination?.total_items || 0,
  };

  const handleRefresh = async () => {
    try {
      toast.success("Refreshing alerts...");
      window.location.reload(); // Simple refresh for now
    } catch (error) {
      toast.error("Failed to refresh");
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title font-bold title-lg-header">Alerts</h1>
          <p className="text-secondary">Monitor and manage system alerts across your infrastructure</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => setIsCreateDialogOpen(true)}
            className="flex items-center gap-1.5 text-sm font-medium"
            style={{ padding: "18px 22px" }}
          >
            <Plus className="h-4 w-4" />
            Create Alert
          </Button>
          <Button
            variant="ghost"
            onClick={handleRefresh}
            className="flex items-center gap-1.5 bg-card text-sm font-medium transition-colors border border-border-medium text-muted-foreground"
            style={{ padding: "18px 22px" }}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <TimeRangeSelector
            value={timeRange}
            onChange={onTimeRangeChange}
            customRange={customTimeRange}
          />
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(value) => {
        setActiveTab(value);
        setSearchParams({ tab: value });
      }} className="w-full">
        <TabsList className="!grid !grid-cols-3 w-full h-12 bg-surface-secondary border-b-0">
          {TAB_CONFIG.map(({ value, label, icon: Icon }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="flex items-center justify-center gap-2 w-full data-[state=active]:bg-card data-[state=active]:shadow-sm"
            >
              <Icon className="h-4 w-4" />
              {label}
              <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-surface-secondary text-secondary border border-border-medium">
                {tabCounts[value]}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Alert Groups Tab */}
        <TabsContent value="groups" className="mt-6">
          <AlertGroupsTabContent
            timeRange={timeRange}
            customTimeRange={customTimeRange}
            onGroupClick={onGroupClick}
          />
        </TabsContent>

        {/* Ungrouped Alerts Tab */}
        <TabsContent value="ungrouped" className="mt-6">
          <AlertsTabContent
            timeRange={timeRange}
            customTimeRange={customTimeRange}
            onAlertClick={onAlertClick}
          />
        </TabsContent>

        {/* All Alerts Tab */}
        <TabsContent value="all" className="mt-6">
          <AllAlertsTabContent
            timeRange={timeRange}
            customTimeRange={customTimeRange}
            onAlertClick={onAlertClick}
          />
        </TabsContent>
      </Tabs>

      {/* Create Alert Dialog */}
      <CreateAlertDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
      />
    </div>
  );
}
