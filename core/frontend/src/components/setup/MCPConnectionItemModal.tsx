import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "./../ui/dialog";
import { Button } from "./../ui/button";
import { Card, CardHeader, CardTitle } from "./../ui/card";
import { MCPConnectionItem } from "./MCPConnectionItem";
import { ConfluenceConnectionItem } from "./ConfluenceConnectionItem";
import { ChevronDown, ChevronRight, Database, Activity, Search, BookOpen } from "lucide-react";
import { HttpHeader } from "./../../types/config";

type MCPConfig =
  | {
      enabled: boolean;
      endpointUrl: string;
      httpHeaders: HttpHeader[];
    }
  | {
      enabled: boolean;
      base_url: string;
      username: string;
      api_token: string;
    };

interface MCPConnectionItemModalProps {
  source: "grafana" | "jaeger" | "opensearch" | "confluence";
  config: MCPConfig;
  onUpdate: (config: MCPConfig) => void;
  onTestConnection: () => void;
  isTesting: boolean;
  testResult: "success" | "error" | null;
  refreshValidationErrors: () => void;
}

export function MCPConnectionItemModal({
  source,
  config,
  onUpdate,
  onTestConnection,
  isTesting,
  testResult,
  refreshValidationErrors
}: MCPConnectionItemModalProps) {
  const [open, setOpen] = useState(false);
  const [tempConfig, setTempConfig] = useState(config);

  const title = source === "grafana" ? "Grafana"
    : source === "jaeger" ? "Jaeger"
    : source === "opensearch" ? "OpenSearch"
    : "Confluence";
  const Icon = source === "grafana" ? Database
    : source === "jaeger" ? Activity
    : source === "opensearch" ? Search
    : BookOpen;
  const description = source === "grafana"
    ? "Connect to Grafana via MCP for dashboard metrics and visualization data"
    : source === "jaeger"
    ? "Connect to Jaeger via MCP for distributed tracing data and analysis"
    : source === "opensearch"
    ? "Connect to OpenSearch via MCP for log search and analytics"
    : "Connect to Confluence to import and sync runbooks from Confluence pages";

  const handleOpen = (isOpen: boolean) => {
    if (isOpen) {
      // When opening, set temp config to current config
      setTempConfig(config);
    }
    setOpen(isOpen);
  };

  const handleSave = () => {
    onUpdate(tempConfig);
    setOpen(false);
  };

  const handleCancel = () => {
    setTempConfig(config);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogTrigger asChild>
        <Card className="box-shadow cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="flex flex-row items-center justify-between py-4">
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="">{title} Configuration</CardTitle>
            </div>
            <Button
              variant="ghost"
              size="sm"
            >
              {true ? (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </Button>
          </CardHeader>
        </Card>
      </DialogTrigger>
      <DialogContent className=" max-h-[90vh] overflow-y-auto" style={{ width: '774px' }}>
        <DialogHeader>
          <DialogTitle className="triage-journey-header flex items-center gap-2">
            <Icon className="h-5 w-5" />
            {title} Configuration
          </DialogTitle>
          <DialogDescription>
            {description}
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          {source === 'confluence' ? (
            <ConfluenceConnectionItem
              config={tempConfig as any}
              onUpdate={(data) => {
                setTempConfig(data);
                onUpdate(data);
              }}
              onTestConnection={onTestConnection}
              isTesting={isTesting}
              testResult={testResult}
              refreshValidationErrors={refreshValidationErrors}
            />
          ) : (
            <MCPConnectionItem
              source={source}
              config={tempConfig as any}
              onUpdate={(data) => {
                setTempConfig(data);
                onUpdate(data);
              }}
              onTestConnection={onTestConnection}
              isTesting={isTesting}
              testResult={testResult}
              refreshValidationErrors={refreshValidationErrors}
            />
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button className="active-range-bg" onClick={handleSave}>
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
