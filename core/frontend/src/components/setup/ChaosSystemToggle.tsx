import { Switch } from "../ui/switch";
import { Card } from "../ui/card";

interface ChaosSystemToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function ChaosSystemToggle({ enabled, onToggle }: ChaosSystemToggleProps) {
  return (
    <Card className="border border-border p-6 box-shadow">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={onToggle}
          />
        </div>

        <div className="flex-1 px-2">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">Chaos System</h3>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Enable or disable the chaos engineering system for testing resilience
          </p>
        </div>
        
      </div>
    </Card>
  );
}
