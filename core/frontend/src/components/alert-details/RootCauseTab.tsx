import { RefreshCw, Clock } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { RootCauseContent } from "./RootCauseContent";

interface RootCauseTabProps {
  alert: any;
  rootCause: any;
  rootCauseLoading: boolean;
  handleManualTriage: () => void;
}

export const RootCauseTab = ({ alert, rootCause, rootCauseLoading, handleManualTriage }: RootCauseTabProps) => {
  return (
    <div className="pb-6">
      <Card className="box-shadow rounded-lg mr-2">
        {/* <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="title">Alert Investigation Summary</CardTitle>
        </CardHeader> */}
        <CardContent className="px-6">
          {rootCauseLoading ? (
            <div className="text-center py-16">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-muted" />
              <p className="text-secondary">Loading root cause analysis...</p>
            </div>
          ) : (alert.triage_status === "success" || alert.triage_status === "error") && rootCause ? (
            <RootCauseContent content={rootCause.content} />
          ) : (alert.triage_status === "pending") ? (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <Clock className="h-6 w-6 text-muted" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Analysis In Pending</h3>
                <p className="text-secondary">
                  <button type="button" onClick={handleManualTriage} className="text-info cursor-pointer underline hover:text-info-dark">Click here</button> or start triage to generate a root cause analysis.
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <Clock className="h-6 w-6 text-muted" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Analysis In Progress</h3>
                <p className="text-secondary">
                  Root cause analysis will be available once triage is completed successfully. Please check back later.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
