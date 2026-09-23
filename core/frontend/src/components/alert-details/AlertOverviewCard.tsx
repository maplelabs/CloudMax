import { InfoIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { StatusChip } from "../status-chip";
import { SeverityChip, SeverityType } from "../severity-chip";
import { formatDate } from "./utils";
import { toTitleCase } from "../../utils/helper";

interface AlertOverviewCardProps {
  alert: any;
}

export const AlertOverviewCard = ({ alert }: AlertOverviewCardProps) => {
  return (
    <Card className="box-shadow rounded-lg mr-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 info-title-text" >
          <InfoIcon size={12}/>
          Alert Overview
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="text-sm font-medium text-tertiary">Alert Name</label>
            <p className="text-foreground">{alert.name}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Alert Status</label>
            <div className="mt-1">
              {toTitleCase(alert.alert_status)}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Severity</label>
            <div className="mt-1">
              <SeverityChip severity={alert.severity as SeverityType} />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Started At</label>
            <p className="text-foreground">{formatDate(alert.started_at)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Alert Source</label>
            <p className="text-foreground font-mono text-sm">{alert.alert_source}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-tertiary">Triage Status</label>
            <div className="mt-1">
              <StatusChip status={alert.triage_status as any} />
            </div>
          </div>
        </div>
        {alert.payload?.annotations?.description && (
          <div>
            <label className="text-sm font-medium text-tertiary">Description</label>
            <p className="text-foreground mt-1">{alert.payload.annotations.description}</p>
          </div>
        )}
        {alert.payload?.annotations?.summary && (
          <div>
            <label className="text-sm font-medium text-tertiary">Summary</label>
            <p className="text-foreground mt-1">{alert.payload.annotations.summary}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
