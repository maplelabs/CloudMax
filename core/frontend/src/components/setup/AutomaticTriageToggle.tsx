import { Switch } from "../ui/switch";
import { Card } from "../ui/card";

interface AutomaticTriageToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function AutomaticTriageToggle({ enabled, onToggle }: AutomaticTriageToggleProps) {
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
            <h3 className="font-bold" style={{fontSize:"15px"}}>Automatic Triaging</h3>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Enable or disable automatic triaging and response for incoming alerts
          </p>
        </div>

      </div>
    </Card>
  );
}

