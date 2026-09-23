import { Card } from "../ui/card";
import { Badge } from "../ui/badge";
import { SeverityChip, SeverityType } from "../severity-chip";

interface GroupOverviewCardProps {
  group: {
    id: string;
    group_name: string;
    alert_count: number;
    severity: string;
    triage_status: string;
    status: string;
    grouping_confidence?: number | null;
    grouping_reasoning?: string | null;
    created_at: string;
    updated_at: string;
    tokens_used?: number | null;
    price_usd?: number | null;
    processing_time_sec?: number | null;
  };
}

export function GroupOverviewCard({ group }: GroupOverviewCardProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const confidencePercent = group.grouping_confidence
    ? Math.round(group.grouping_confidence * 100)
    : null;

  return (
    <Card className="p-6" style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h2 className="text-xl font-bold text-foreground mb-6">Group Overview</h2>
        </div>

        {/* 2-Column Grid Layout - Always 2 columns */}
        <div className="grid grid-cols-2 gap-x-12 gap-y-6">
          {/* Left Column */}
          <div className="space-y-6">
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">GROUP NAME</p>
              <p className="text-base text-foreground">{group.group_name}</p>
            </div>

            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">STATUS</p>
              <Badge
                variant={group.status === "active" ? "default" : "secondary"}
                className={`capitalize ${group.status === "active" ? "bg-green-100 text-green-700 border-green-300" : "bg-gray-100 text-gray-700 border-gray-300"}`}
              >
                {group.status}
              </Badge>
            </div>

            {confidencePercent !== null && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">CONFIDENCE SCORE</p>
                <p className="text-base font-semibold text-foreground">{confidencePercent}%</p>
              </div>
            )}

            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">LAST UPDATE</p>
              <p className="text-base text-foreground">{formatDate(group.updated_at)}</p>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">SEVERITY</p>
              <SeverityChip severity={group.severity as SeverityType} />
            </div>

            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">TOTAL ALERTS</p>
              <p className="text-base font-semibold text-foreground">{group.alert_count}</p>
            </div>

            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">CREATED</p>
              <p className="text-base text-foreground">{formatDate(group.created_at)}</p>
            </div>
          </div>
        </div>

        {/* Description Section - Full Width */}
        {group.grouping_reasoning && (
          <div className="pt-4 border-t border-border-medium">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">DESCRIPTION</p>
            <p className="text-base text-foreground leading-relaxed">{group.grouping_reasoning}</p>
          </div>
        )}
      </div>
    </Card>
  );
}
