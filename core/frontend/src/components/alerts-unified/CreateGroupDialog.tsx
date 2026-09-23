import { useState } from "react";
import { Layers } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { Label } from "../ui/label";

interface Alert {
  id: string;
  name: string;
}

interface CreateGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedAlerts: Alert[];
  onCreateGroup: (groupName: string, description: string) => void;
  isCreating?: boolean;
}

export function CreateGroupDialog({
  open,
  onOpenChange,
  selectedAlerts,
  onCreateGroup,
  isCreating = false,
}: CreateGroupDialogProps) {
  const [groupName, setGroupName] = useState("");
  const [description, setDescription] = useState("");

  const handleCreate = () => {
    if (groupName.trim()) {
      onCreateGroup(groupName.trim(), description.trim());
    }
  };

  const handleCancel = () => {
    setGroupName("");
    setDescription("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">Create Alert Group</DialogTitle>
          <p className="text-sm text-muted-foreground mt-2">
            {selectedAlerts.length} alert(s) will be grouped
          </p>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Group Name Input */}
          <div className="space-y-2">
            <Label htmlFor="group-name" className="text-sm font-semibold">
              Group Name <span className="text-red-500">*</span>
            </Label>
            <Input
              id="group-name"
              placeholder="Enter group name..."
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              disabled={isCreating}
              className="w-full"
            />
          </div>

          {/* Description Textarea */}
          <div className="space-y-2">
            <Label htmlFor="description" className="text-sm font-semibold">
              Description
            </Label>
            <Textarea
              id="description"
              placeholder="What does this group represent?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isCreating}
              className="w-full min-h-[100px] resize-none"
            />
          </div>

          {/* Alerts being grouped */}
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Alerts being grouped:</Label>
            <div className="max-h-[150px] overflow-y-auto border border-border rounded-md p-3 bg-muted/30">
              {selectedAlerts.map((alert) => (
                <div key={alert.id} className="text-sm text-foreground py-1">
                  #{alert.id} {alert.name}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button
            variant="outline"
            onClick={handleCancel}
            disabled={isCreating}
          >
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={isCreating || !groupName.trim()}
            className="bg-primary hover:bg-primary/90"
          >
            {isCreating ? (
              <>
                <Layers className="mr-2 h-4 w-4 animate-pulse" />
                Creating...
              </>
            ) : (
              <>
                <Layers className="mr-2 h-4 w-4" />
                Create Group
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
