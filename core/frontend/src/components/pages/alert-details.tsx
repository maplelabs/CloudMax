import { useState, useEffect } from "react";
import { RefreshCw, ChevronLeft, AlertCircle, Activity, FileText, Play, ClipboardCheck } from "lucide-react";
import { Button } from "../ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { toast } from "sonner";
import { useAlert, useRootCauseAnalysis, useTriage, useAlertEvaluation, useStartTriage } from "../../hooks/useAlerts";
import { useConfig } from "../../hooks/useConfig";
import { AlertOverviewCard } from "../alert-details/AlertOverviewCard";
import { AlertLabelsCard } from "../alert-details/AlertLabelsCard";
import { TechnicalDetailsCard } from "../alert-details/TechnicalDetailsCard";
import { RootCauseTab } from "../alert-details/RootCauseTab";
import { TriageJourneyTab } from "../alert-details/TriageJourneyTab";
import { EvaluationTab } from "../alert-details/EvaluationTab";

interface AlertDetailsProps {
  alertId: string;
  onBack: () => void;
  defaultTab?: string;
}

export function AlertDetails({ alertId, onBack, defaultTab }: AlertDetailsProps) {
  // Fetch data using API hooks
  const { data: alert, isLoading: alertLoading, error: alertError, refetch: refetchAlert } = useAlert(alertId);
  const { data: rootCause, isLoading: rootCauseLoading, refetch: refetchRootCause } = useRootCauseAnalysis(alertId);
  const { data: triage, isLoading: triageLoading, refetch: refetchTriage } = useTriage(alertId);
  const { data: alertEvaluation, isLoading: alertEvaluationLoading, refetch: refetchAlertEvaluation } = useAlertEvaluation(alertId);

  // Fetch config to check automatic_triage setting
  const { config } = useConfig();
  const startTriageMutation = useStartTriage();

  const [activeTab, setActiveTab] = useState(defaultTab || "alert-info");
  const [refreshingTab, setRefreshingTab] = useState<string | null>(null);
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [triggeringTriage, setTriggeringTriage] = useState(false);

  // Scroll to top when component mounts or alertId changes
  useEffect(() => {
    // Find the main content scrollable container and scroll to top
    const mainContent = document.querySelector('main');
    if (mainContent) {
      mainContent.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [alertId]);

  // Show loading state if alert is not loaded yet
  if (alertLoading) {
    return (
      <div className="p-6 space-y-6 min-h-screen">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-muted" />
            <p className="text-secondary">Loading alert details...</p>
          </div>
        </div>
      </div>
    );
  }

  // Show error state if alert failed to load
  if (alertError || !alert) {
    return (
      <div className="p-6 space-y-6 min-h-screen">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <p className="text-danger mb-4">Failed to load alert details</p>
            <Button onClick={onBack} variant="outline">Back to Alerts</Button>
          </div>
        </div>
      </div>
    );
  }

  // Set default tab based on triage status once alert is loaded
  if (defaultTab === undefined && alert.triage_status === "success") {
    setActiveTab("root-cause");
  }

  const handleTriageRefresh = async () => {
    setRefreshingTab('triage-journey');
    await refetchAlert();
    await refetchTriage();
    await refetchRootCause();
    await refetchAlertEvaluation();
    setRefreshingTab(null);
    toast.success("Triage journey refreshed");
  };

  const handleRefreshAll = async () => {
    setRefreshingAll(true);
    try {
      await Promise.all([
        refetchAlert(),
        refetchRootCause(),
        refetchTriage(),
        refetchAlertEvaluation()
      ]);
      toast.success("Alert data refreshed");
    } catch (error) {
      toast.error("Failed to refresh data");
    } finally {
      setRefreshingAll(false);
    }
  };

  const handleManualTriage = async () => {
    setTriggeringTriage(true);
    try {
      await startTriageMutation.mutateAsync(alertId);
      toast.success("Manual triage started successfully");
      await Promise.all([
        refetchAlert(),
        refetchRootCause(),
        refetchTriage(),
        refetchAlertEvaluation()
      ]);
    } catch (error: any) {
      console.error("Failed to start manual triage:", error);
      toast.error(error?.response?.data?.detail || "Failed to start manual triage");
    } finally {
      setTriggeringTriage(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="flex-shrink-0 px-6 pt-6 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={onBack}
              className="gap-2 text-slate-600 hover:text-slate-900 self-start"
            >
              <ChevronLeft className="h-4 w-4" />
              Back to Alerts
            </Button>
            <h1 className="page-title text-bold title-lg-header px-4">{alert.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={handleRefreshAll}
              disabled={refreshingAll}
              className="flex items-center gap-1.5 bg-card text-sm font-medium transition-colors border border-border-medium text-muted-foreground"
             style={{ padding: "18px 22px" }}
            >
              <RefreshCw className={`h-4 w-4 ${refreshingAll ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            {config?.automatic_triage === false && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleManualTriage}
                disabled={triggeringTriage || alert.triage_status === 'processing' || alert.triage_status === 'queued'}
                className="gap-2"
              >
                {triggeringTriage ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                Start Triage
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col flex-1 overflow-hidden px-6">
        <TabsList className="w-full">
          <TabsTrigger value="alert-info" className="tab-title-text">
            <AlertCircle className="h-4 w-4" />
            Alert Information
          </TabsTrigger>
          <TabsTrigger value="root-cause" className="tab-title-text">
            <Activity className="h-4 w-4"/>
            Root Cause
          </TabsTrigger>
          <TabsTrigger value="triage-journey" className="relative tab-title-text">
            <FileText className="h-4 w-4" />
            Triage Journey
            {alert.triage_status === "processing" && (
              <div className="absolute -top-2 -right-1 h-2 w-2 bg-info rounded-full animate-pulse" />
            )}
          </TabsTrigger>
          <TabsTrigger value="evaluation" className="tab-title-text">
            <ClipboardCheck className="h-4 w-4" />
            Evaluation Details
          </TabsTrigger>
        </TabsList>
        <div style={{ height: 'calc(100vh - 250px)' , scrollBehavior: "smooth", overflowY: "scroll",marginTop:"10px" }}>
          <TabsContent value="alert-info" className="flex-1 overflow-y-auto mt-6">
            <div className="space-y-6 pb-6">
              <AlertOverviewCard alert={alert} />
              <AlertLabelsCard labels={alert.payload?.labels || {}} />
              <TechnicalDetailsCard alert={alert} />
            </div>
          </TabsContent>

          <TabsContent value="root-cause" className="flex-1 mt-6">
            <RootCauseTab
              alert={alert}
              rootCause={rootCause}
              rootCauseLoading={rootCauseLoading}
              handleManualTriage={handleManualTriage}
            />
          </TabsContent>

          <TabsContent value="triage-journey" className="flex-1 overflow-y-auto mt-6">
            <TriageJourneyTab
              alert={alert}
              triage={triage}
              triageLoading={triageLoading}
              refreshingTab={refreshingTab}
              handleTriageRefresh={handleTriageRefresh}
            />
          </TabsContent>

          <TabsContent value="evaluation" className="flex-1 overflow-y-auto mt-6">
            <EvaluationTab
              alert={alert}
              alertEvaluation={alertEvaluation}
              alertEvaluationLoading={alertEvaluationLoading}
            />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
