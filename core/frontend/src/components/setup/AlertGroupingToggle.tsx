import { Switch } from "../ui/switch";
import { Card } from "../ui/card";

interface AlertGroupingToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function AlertGroupingToggle({ enabled, onToggle }: AlertGroupingToggleProps) {
  return (
    <Card className="border border-border p-6 box-shadow">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={onToggle}
          />
        </div>
        <div className="flex-1 ml-6">
          <div className="flex items-center gap-2">
            <h3 className="font-bold" style={{fontSize:"15px"}}>Alert Grouping</h3>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Enable or disable automatic grouping and correlation of related alerts
          </p>
        </div>
      </div>
    </Card>
  );
}
