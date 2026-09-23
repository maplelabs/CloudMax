import { useState, useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

interface DeleteGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupName: string;
  alertCount: number;
  onConfirm: () => void;
  isDeleting?: boolean;
}

export function DeleteGroupDialog({
  open,
  onOpenChange,
  groupName,
  alertCount,
  onConfirm,
  isDeleting = false,
}: DeleteGroupDialogProps) {
  const [confirmText, setConfirmText] = useState("");

  // Reset confirmation text when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setConfirmText("");
    }
  }, [open]);

  const isConfirmed = confirmText === "DELETE";

  const handleConfirm = () => {
    if (isConfirmed) {
      onConfirm();
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-red-600" />
            Delete Alert Group
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base space-y-4">
            <p>
              Are you sure you want to delete the group{" "}
              <span className="font-semibold text-foreground">"{groupName}"</span>?
            </p>
            <p className="text-sm text-muted-foreground">
              This will ungroup <span className="font-semibold text-foreground">{alertCount} alert{alertCount !== 1 ? 's' : ''}</span> and
              they will appear in the "Ungrouped Alerts" tab.
            </p>
            <div className="space-y-2">
              <Label htmlFor="confirm-delete" className="text-sm font-semibold text-foreground">
                Type <span className="text-red-600 font-mono">DELETE</span> to confirm:
              </Label>
              <Input
                id="confirm-delete"
                placeholder="DELETE"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                disabled={isDeleting}
                className="font-mono"
                autoComplete="off"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              This action cannot be undone.
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleConfirm();
            }}
            disabled={isDeleting || !isConfirmed}
            className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
          >
            {isDeleting ? "Deleting..." : "Delete Group"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
