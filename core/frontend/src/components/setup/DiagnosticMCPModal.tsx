import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "./../ui/dialog";
import { Button } from "./../ui/button";
import { Card, CardHeader, CardTitle } from "./../ui/card";
import { DiagnosticMCPItem } from "./DiagnosticMCPItem";
import { ChevronRight, Stethoscope, Trash2 } from "lucide-react";
import { DiagnosticMcpServer } from "./../../types/config";

interface DiagnosticMCPModalProps {
  server: DiagnosticMcpServer;
  index: number;
  onUpdate: (server: DiagnosticMcpServer) => void;
  onDelete: () => void;
  onTestConnection?: () => void;
  isTesting?: boolean;
  testResult?: "success" | "error" | null;
  refreshValidationErrors?: () => void;
}

export function DiagnosticMCPModal({
  server,
  index,
  onUpdate,
  onDelete,
  onTestConnection,
  isTesting,
  testResult,
  refreshValidationErrors
}: DiagnosticMCPModalProps) {
  const [open, setOpen] = useState(false);
  const [tempConfig, setTempConfig] = useState(server);
  const [originalConfig, setOriginalConfig] = useState(server);

  const handleOpen = (isOpen: boolean) => {
    if (isOpen) {
      // When opening, save original config and set temp config to current config
      setOriginalConfig(server);
      setTempConfig(server);
    }
    setOpen(isOpen);
  };

  const handleConfigUpdate = (updatedConfig: DiagnosticMcpServer) => {
    setTempConfig(updatedConfig);
    // Update parent immediately so test connection uses latest values
    onUpdate(updatedConfig);
  };

  const handleSave = () => {
    onUpdate(tempConfig);
    setOpen(false);
  };

  const handleCancel = () => {
    // Revert to original config
    setTempConfig(originalConfig);
    onUpdate(originalConfig);
    setOpen(false);
  };

  const handleDelete = () => {
    onDelete();
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogTrigger asChild>
        <Card className="box-shadow cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="flex flex-row items-center justify-between py-4">
            <div className="flex items-center gap-2">
              <Stethoscope className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="">
                {server.name || `Diagnostic Server ${index + 1}`}
              </CardTitle>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete();
                }}
                className="h-8 w-8 p-0 text-muted-foreground hover:text-red-600"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
              >
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          </CardHeader>
        </Card>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto" style={{ width: '774px', maxHeight:"80vh" }}>
        <DialogHeader>
          <DialogTitle className="triage-journey-header">Diagnostic MCP Server Configuration</DialogTitle>
        </DialogHeader>
        <div style={{height:"60vh", overflowY:"scroll", padding:10}}>
          <DiagnosticMCPItem
            config={tempConfig}
            onUpdate={handleConfigUpdate}
            onTestConnection={onTestConnection}
            isTesting={isTesting}
            testResult={testResult}
            refreshValidationErrors={refreshValidationErrors}
          />
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button
            variant="outline"
            onClick={handleDelete}
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            Delete Server
          </Button>
          <Button className="active-range-bg" onClick={handleSave}>
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

