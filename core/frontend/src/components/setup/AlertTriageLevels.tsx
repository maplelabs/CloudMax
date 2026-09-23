import { Switch } from "./../ui/switch";
import { Label } from "./../ui/label";
import { Card, CardHeader, CardTitle } from "./../ui/card";
import {InfoIcon } from "lucide-react";

interface AlertTriageLevelsProps {
  triageLevels: {
    p1: boolean;
    p2: boolean;
    p3: boolean;
  };
  onUpdate: (level: "p1" | "p2" | "p3", enabled: boolean) => void;
}

export function AlertTriageLevels({ triageLevels, onUpdate }: AlertTriageLevelsProps) {
  return (
    <Card className="box-shadow px-0">
      <CardHeader>
        <CardTitle className="font-bold" style={{fontSize:"18px"}}>Alert Triage Levels</CardTitle>
      </CardHeader>
      <div>
        <div className="text-sm text-muted-foreground mb-4 px-6">
          Select which priority levels should trigger automated triage. Each level can be enabled independently.
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between py-4 px-6 ">
            <div className="flex items-center space-x-2">
              <Switch
                id="p1-switch"
                checked={triageLevels.p1}
                onCheckedChange={(checked) => onUpdate("p1", checked)}
              />
              <Label htmlFor="p1-switch" className="font-medium text-foreground">P1 - Critical</Label>
            </div>
            <div className="text-sm text-muted-foreground">Immediate response required</div>
          </div>

          <div className="border-b" />

          <div className="flex items-center justify-between py-4 px-6">
            <div className="flex items-center space-x-2">
              <Switch
                id="p2-switch"
                checked={triageLevels.p2}
                onCheckedChange={(checked) => onUpdate("p2", checked)}
              />
              <Label htmlFor="p2-switch" className="font-medium text-foreground">P2 - High</Label>
            </div>
            <div className="text-sm text-muted-foreground">Response within 4 hours</div>
          </div>
          <div className="border-b" />
          <div className="flex items-center justify-between py-4 px-6">
            <div className="flex items-center space-x-2">
              <Switch
                id="p3-switch"
                checked={triageLevels.p3}
                onCheckedChange={(checked) => onUpdate("p3", checked)}
              />
              <Label htmlFor="p3-switch" className="font-medium text-foreground">P3 - Medium</Label>
            </div>
            <div className="text-sm text-muted-foreground">Response within 24 hours</div>
          </div>
          <div className="border-b" />
        </div>

        <div className="p-3 py-6 text-sm text-success-text" style={{background:"#F3F4F6"}}>
          <div className="flex items-start">
            <InfoIcon className="h-4 w-4 mt-0.5 text-success" />
            <div className="px-1">
              Each priority level can be enabled or disabled independently based on your triage requirements.
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}