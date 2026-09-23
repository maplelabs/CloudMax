import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { RefreshCw, ChevronLeft, AlertCircle, Activity, FileText, Info, Loader2, ClipboardCheck, Plus, Trash2 } from "lucide-react";
import { Button } from "../ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { Card } from "../ui/card";
import { toast } from "sonner";
import { GroupOverviewCard } from "../alert-group-details/GroupOverviewCard";
import { GroupRootCauseTab } from "../alert-group-details/GroupRootCauseTab";
import { GroupTriageJourneyTab } from "../alert-group-details/GroupTriageJourneyTab";
import { GroupEvaluationTab } from "../alert-group-details/GroupEvaluationTab";
import { GroupAlertsTab } from "../alert-group-details/GroupAlertsTab";
import { AddAlertsToGroupDialog } from "../alert-group-details/AddAlertsToGroupDialog";
import { DeleteGroupDialog } from "../alert-group-details/DeleteGroupDialog";
import {
  useAlertGroupDetail,
  useGroupTriage,
  useGroupRootCause,
  useGroupEvaluation
} from "../../hooks/useAlertGroupDetails";
import { useUngroupedAlerts } from "../../hooks/useUngroupedAlerts";
import apiClient from "../../service/api";

export function AlertGroupDetails() {
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("group-info");
  const [showAddAlertsDialog, setShowAddAlertsDialog] = useState(false);
  const [isAddingAlerts, setIsAddingAlerts] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Fetch alert group data
  const { data: groupData, isLoading, error, refetch } = useAlertGroupDetail(groupId || "");
  const { data: triageData, refetch: refetchTriage } = useGroupTriage(groupId || "");
  const { data: rcaData, refetch: refetchRCA } = useGroupRootCause(groupId || "");
  const { data: evaluationData, isLoading: evaluationLoading, refetch: refetchEvaluation } = useGroupEvaluation(groupId || "");

  // Fetch ungrouped alerts for adding to this group
  const { data: ungroupedAlertsData } = useUngroupedAlerts({
    page: 1,
    page_size: 100,
  });

  const handleBack = () => {
    // Navigate to alerts page with groups tab selected
    navigate("/alerts?tab=groups");
  };

  const handleRefresh = async () => {
    try {
      await Promise.all([
        refetch(),
        refetchTriage(),
        refetchRCA(),
        refetchEvaluation()
      ]);
      toast.success("Group data refreshed");
    } catch (error) {
      toast.error("Failed to refresh group data");
    }
  };

  const handleAlertClick = (alertId: number) => {
    navigate(`/alerts/${alertId}`);
  };

  const handleAddAlerts = async (alertIds: string[]) => {
    if (!groupId) return;

    setIsAddingAlerts(true);
    try {
      await apiClient.post(`/alert-groups/${groupId}/alerts`, {
        alert_ids: alertIds
      });

      toast.success(`${alertIds.length} alert(s) added to group successfully`);
      setShowAddAlertsDialog(false);
      await refetch(); // Refetch group data to show new alerts
    } catch (error: any) {
      console.error("Failed to add alerts to group:", error);
      const errorMessage = error?.response?.data?.detail || "Failed to add alerts to group";
      toast.error(errorMessage);
    } finally {
      setIsAddingAlerts(false);
    }
  };

  const handleRemoveAlerts = async (alertIds: number[]) => {
    if (!groupId) return;

    try {
      await apiClient.delete(`/alert-groups/${groupId}/alerts`, {
        data: {
          alert_ids: alertIds.map(String)
        }
      });

      toast.success(`${alertIds.length} alert(s) removed from group. They are now individual ungrouped alerts.`);
      await refetch(); // Refetch group data to update alerts list
    } catch (error: any) {
      console.error("Failed to remove alerts from group:", error);
      const errorMessage = error?.response?.data?.detail || "Failed to remove alerts from group";
      toast.error(errorMessage);
      throw error; // Re-throw so the component can handle the error state
    }
  };

  const handleDeleteGroup = async () => {
    if (!groupId) return;

    setIsDeleting(true);
    try {
      const response = await apiClient.delete(`/alert-groups/${groupId}`);

      toast.success(response.data.message || `Group deleted successfully. ${groupData.alerts.length} alert(s) are now ungrouped.`);
      setShowDeleteDialog(false);

      // Navigate back to alerts page, ungrouped tab
      navigate('/alerts?tab=ungrouped');
    } catch (error: any) {
      console.error("Failed to delete group:", error);
      const errorMessage = error?.response?.data?.detail || "Failed to delete group";
      toast.error(errorMessage);
    } finally {
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <h3 className="text-lg font-semibold">Loading group details...</h3>
        </div>
      </div>
    );
  }

  if (error || !groupData) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Card className="p-8 max-w-md">
          <div className="text-center">
            <AlertCircle className="h-12 w-12 text-danger mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Failed to Load Group</h3>
            <p className="text-sm text-muted-foreground mb-4">
              {error instanceof Error ? error.message : "Group not found"}
            </p>
            <div className="flex gap-2 justify-center">
              <Button onClick={() => refetch()} variant="outline">Retry</Button>
              <Button onClick={handleBack}>Back to Alerts</Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b bg-card">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            onClick={handleBack}
            className="flex items-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft className="h-4 w-4" />
            Back to Alert Groups
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={handleRefresh}
            className="flex items-center gap-1.5"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowAddAlertsDialog(true)}
            disabled={groupData.triage_status === "in_progress"}
            className="flex items-center gap-1.5"
          >
            <Plus className="h-4 w-4" />
            Add Alerts
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowDeleteDialog(true)}
            disabled={groupData.triage_status === "in_progress" || isDeleting}
            className="flex items-center gap-1.5 text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <Trash2 className="h-4 w-4" />
            Delete Group
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto">
          {/* Group Name Header */}
          <div className="px-6 pt-6 pb-4">
            <h1 className="page-title text-bold title-lg-header">{groupData.group_name}</h1>
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full px-6">
            <TabsList className="w-full">
              <TabsTrigger value="group-info" className="tab-title-text">
                <Info className="h-4 w-4" />
                Group Information
              </TabsTrigger>
              <TabsTrigger value="root-cause" className="tab-title-text">
                <Activity className="h-4 w-4" />
                Root Cause
              </TabsTrigger>
              <TabsTrigger value="triage-journey" className="tab-title-text">
                <FileText className="h-4 w-4" />
                Triage Journey
              </TabsTrigger>
              <TabsTrigger value="evaluation" className="tab-title-text">
                <ClipboardCheck className="h-4 w-4" />
                Evaluation Details
              </TabsTrigger>
            </TabsList>

            <div style={{ height: 'calc(100vh - 250px)', scrollBehavior: "smooth", overflowY: "scroll", marginTop: "10px" }}>
              <TabsContent value="group-info" className="flex-1 overflow-y-auto mt-6">
                <div className="space-y-6 pb-6">
                  <GroupOverviewCard group={groupData} />
                  <GroupAlertsTab
                    alerts={groupData.alerts}
                    onAlertClick={handleAlertClick}
                    onRemoveAlerts={handleRemoveAlerts}
                    isTriaging={groupData.triage_status === "in_progress"}
                  />
                </div>
              </TabsContent>

              <TabsContent value="root-cause" className="flex-1 mt-6">
                <GroupRootCauseTab rootCause={rcaData} />
              </TabsContent>

              <TabsContent value="triage-journey" className="flex-1 overflow-y-auto mt-6">
                <GroupTriageJourneyTab
                  journey={triageData?.messages || []}
                  triageStatus={groupData.triage_status}
                  updatedAt={groupData.updated_at}
                />
              </TabsContent>

              <TabsContent value="evaluation" className="flex-1 overflow-y-auto mt-6">
                <GroupEvaluationTab
                  evaluation={evaluationData}
                  evaluationLoading={evaluationLoading}
                  evaluationStatus={
                    // Use actual status from backend if available
                    evaluationData?.status ||
                    // Fallback: If scores exist, evaluation is successful
                    (evaluationData?.score_criteria_cards?.length > 0 ? "success" : "pending")
                  }
                />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>

      {/* Add Alerts Dialog */}
      <AddAlertsToGroupDialog
        open={showAddAlertsDialog}
        onOpenChange={setShowAddAlertsDialog}
        groupName={groupData.group_name}
        ungroupedAlerts={ungroupedAlertsData?.alerts || []}
        onAddAlerts={handleAddAlerts}
        isAdding={isAddingAlerts}
      />

      {/* Delete Group Dialog */}
      <DeleteGroupDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        groupName={groupData.group_name}
        alertCount={groupData.alerts.length}
        onConfirm={handleDeleteGroup}
        isDeleting={isDeleting}
      />
    </div>
  );
}
