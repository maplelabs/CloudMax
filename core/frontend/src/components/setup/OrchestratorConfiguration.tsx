import { Card, CardContent, CardHeader, CardTitle } from "./../ui/card";
import { Label } from "./../ui/label";
import { Input } from "./../ui/input";
import { AlertTriangle } from "lucide-react";

interface OrchestratorConfigurationProps {
  orchestratorAgents: number;
  onUpdate: (agents: number) => void;
}

export function OrchestratorConfiguration({
  orchestratorAgents,
  onUpdate
}: OrchestratorConfigurationProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Orchestrator Configuration</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-sm text-muted-foreground mb-4">
          Configure the number of agent instances for handling concurrent operations.
        </div>

        <div className="space-y-2">
          <Label htmlFor="orchestrator-agents">Number of Orchestrator Agents</Label>
          <div className="flex items-center space-x-4">
            <Input
              id="orchestrator-agents"
              type="number"
              min="1"
              max="20"
              value={orchestratorAgents}
              onChange={(e) => onUpdate(parseInt(e.target.value) || 1)}
              className="w-24"
            />
            <div className="text-sm text-muted-foreground">
              Recommended: 3-8 agents for optimal performance
            </div>
          </div>
        </div>

        <div className="bg-surface border border-border rounded-lg p-3 text-sm text-muted-foreground">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 text-muted-foreground" />
            <div>
              Higher agent counts improve concurrent processing but may increase resource usage.
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}