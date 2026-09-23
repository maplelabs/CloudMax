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

interface RemoveAlertsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCount: number;
  onConfirm: () => void;
  isRemoving?: boolean;
}

export function RemoveAlertsDialog({
  open,
  onOpenChange,
  selectedCount,
  onConfirm,
  isRemoving = false,
}: RemoveAlertsDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-600" />
            Remove Alerts from Group
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base">
            Are you sure you want to remove {selectedCount} alert{selectedCount !== 1 ? 's' : ''} from this group?
            <br />
            <br />
            <span className="font-medium text-foreground">
              The removed alerts will become individual ungrouped alerts and will appear in the "Ungrouped Alerts" tab.
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isRemoving}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
            disabled={isRemoving}
            className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
          >
            {isRemoving ? "Removing..." : "Remove from Group"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
