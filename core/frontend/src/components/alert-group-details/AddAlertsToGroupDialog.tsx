import { useState } from "react";
import { Search } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Checkbox } from "../ui/checkbox";
import { StatusChip, StatusType } from "../status-chip";
import { SeverityChip, SeverityType } from "../severity-chip";

interface UngroupedAlert {
  id: string;
  name: string;
  severity: string;
  triage_status: string;
}

interface AddAlertsToGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupName: string;
  ungroupedAlerts: UngroupedAlert[];
  onAddAlerts: (alertIds: string[]) => void;
  isAdding?: boolean;
}

export function AddAlertsToGroupDialog({
  open,
  onOpenChange,
  groupName,
  ungroupedAlerts,
  onAddAlerts,
  isAdding = false,
}: AddAlertsToGroupDialogProps) {
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState("");

  const filteredAlerts = ungroupedAlerts.filter((alert) =>
    alert.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    alert.id.includes(searchTerm)
  );

  const handleToggleAlert = (alertId: string) => {
    const newSelection = new Set(selectedAlerts);
    if (newSelection.has(alertId)) {
      newSelection.delete(alertId);
    } else {
      newSelection.add(alertId);
    }
    setSelectedAlerts(newSelection);
  };

  const handleAdd = () => {
    if (selectedAlerts.size > 0) {
      onAddAlerts(Array.from(selectedAlerts));
      setSelectedAlerts(new Set());
      setSearchTerm("");
    }
  };

  const handleCancel = () => {
    setSelectedAlerts(new Set());
    setSearchTerm("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[800px]">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">Add Alerts to Group</DialogTitle>
          <p className="text-sm text-muted-foreground mt-2">
            Select ungrouped alerts to add to "{groupName}"
          </p>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Search Input */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search alerts..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              disabled={isAdding}
              className="pl-10"
            />
          </div>

          {/* Alerts List */}
          <div className="border border-border rounded-md max-h-[400px] overflow-y-auto">
            {filteredAlerts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                {searchTerm ? "No alerts found matching your search" : "No ungrouped alerts available"}
              </div>
            ) : (
              <div className="divide-y divide-border">
                {filteredAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="flex items-center gap-4 p-4 hover:bg-muted/50 cursor-pointer"
                    onClick={() => handleToggleAlert(alert.id)}
                  >
                    <Checkbox
                      checked={selectedAlerts.has(alert.id)}
                      onCheckedChange={() => handleToggleAlert(alert.id)}
                      disabled={isAdding}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">#{alert.id}</span>
                        <SeverityChip severity={alert.severity as SeverityType} />
                      </div>
                      <div className="font-medium text-foreground mt-1">{alert.name}</div>
                    </div>
                    <div>
                      <StatusChip status={alert.triage_status as StatusType} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {selectedAlerts.size > 0 && (
            <div className="text-sm text-muted-foreground">
              {selectedAlerts.size} alert{selectedAlerts.size !== 1 ? 's' : ''} selected
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button variant="outline" onClick={handleCancel} disabled={isAdding}>
            Cancel
          </Button>
          <Button
            onClick={handleAdd}
            disabled={isAdding || selectedAlerts.size === 0}
            className="bg-primary hover:bg-primary/90"
          >
            {isAdding ? "Adding..." : "Add Alerts"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
