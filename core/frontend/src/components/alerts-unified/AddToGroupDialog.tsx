import { useState } from "react";
import { Layers, Search } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { RadioGroup, RadioGroupItem } from "../ui/radio-group";

interface Alert {
  id: string;
  name: string;
}

interface ExistingGroup {
  id: string;
  group_name: string;
  alert_count: number;
}

interface AddToGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedAlerts: Alert[];
  existingGroups: ExistingGroup[];
  onAddToGroup: (groupId: string) => void;
  isAdding?: boolean;
}

export function AddToGroupDialog({
  open,
  onOpenChange,
  selectedAlerts,
  existingGroups,
  onAddToGroup,
  isAdding = false,
}: AddToGroupDialogProps) {
  const [selectedGroupId, setSelectedGroupId] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState("");

  const filteredGroups = existingGroups.filter((group) =>
    group.group_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAdd = () => {
    if (selectedGroupId) {
      onAddToGroup(selectedGroupId);
    }
  };

  const handleCancel = () => {
    setSelectedGroupId("");
    setSearchTerm("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-hidden flex flex-col gap-0 p-0">
        {/* Header - Fixed at top */}
        <div className="px-6 pt-6 pb-4 border-b">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold">Add to Existing Group</DialogTitle>
            <p className="text-sm text-muted-foreground mt-2">
              {selectedAlerts.length} alert(s) will be added to the selected group
            </p>
          </DialogHeader>
        </div>

        {/* Scrollable content area */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {/* Search Input */}
          <div className="space-y-2">
            <Label htmlFor="search" className="text-sm font-semibold">
              Search Groups
            </Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="search"
                placeholder="Search by group name..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                disabled={isAdding}
                className="pl-10"
              />
            </div>
          </div>

          {/* Group Selection */}
          <div className="space-y-2 pb-2">
            <Label className="text-sm font-semibold">
              Select Group <span className="text-red-500">*</span>
            </Label>
            <div className="border border-border rounded-md p-3 bg-muted/30 max-h-[300px] overflow-y-auto">
              {filteredGroups.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No groups found
                </p>
              ) : (
                <RadioGroup value={selectedGroupId} onValueChange={setSelectedGroupId}>
                  <div className="space-y-2">
                    {filteredGroups.map((group) => (
                      <div
                        key={group.id}
                        className="flex items-center space-x-3 p-2 rounded hover:bg-muted/50 cursor-pointer"
                      >
                        <RadioGroupItem value={group.id} id={group.id} />
                        <label
                          htmlFor={group.id}
                          className="flex-1 cursor-pointer text-sm"
                        >
                          <div className="font-medium">{group.group_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {group.alert_count} alerts
                          </div>
                        </label>
                      </div>
                    ))}
                  </div>
                </RadioGroup>
              )}
            </div>
          </div>
        </div>

        {/* Fixed Action Buttons at bottom */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t bg-background">
          <Button variant="outline" onClick={handleCancel} disabled={isAdding}>
            Cancel
          </Button>
          <Button
            onClick={handleAdd}
            disabled={isAdding || !selectedGroupId}
            className="bg-primary hover:bg-primary/90"
          >
            {isAdding ? (
              <>
                <Layers className="mr-2 h-4 w-4 animate-pulse" />
                Adding...
              </>
            ) : (
              "Add to Group"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
