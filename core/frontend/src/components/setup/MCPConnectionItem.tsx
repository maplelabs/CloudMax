import { Label } from "./../ui/label";
import { Switch } from "./../ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./../ui/select";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { Plus, Trash2, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { HttpHeader } from "./../../types/config";

interface MCPConnectionItemProps {
  source: "grafana" | "jaeger" | "opensearch";
  config: {
    enabled: boolean;
    endpointUrl: string;
    httpHeaders: HttpHeader[];
  };
  onUpdate: (config: {
    enabled: boolean;
    endpointUrl: string;
    httpHeaders: HttpHeader[];
  }) => void;
  onTestConnection: () => void;
  isTesting: boolean;
  testResult: "success" | "error" | null;
  refreshValidationErrors: () => void;
}

export function MCPConnectionItem({
  source,
  config,
  onUpdate,
  onTestConnection,
  isTesting,
  testResult,
  refreshValidationErrors
}: MCPConnectionItemProps) {
  const title = source === "grafana" ? "Grafana" : source === "jaeger" ? "Jaeger" : "OpenSearch";
  // Icon for future use: const Icon = source === "grafana" ? Database : source === "jaeger" ? Activity : Search;

  const addHttpHeader = () => {
    onUpdate({
      ...config,
      httpHeaders: [...config.httpHeaders, { key: '', value: '' }]
    });
  };

  const removeHttpHeader = (index: number) => {
    onUpdate({
      ...config,
      httpHeaders: config.httpHeaders.filter((_, i) => i !== index)
    });
  };

  const updateHttpHeader = (index: number, field: 'key' | 'value', value: string) => {
    onUpdate({
      ...config,
      httpHeaders: config.httpHeaders.map((header, i) =>
        i === index ? { ...header, [field]: value } : header
      )
    });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg flex items-center justify-between bg-surface-secondary p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            {/* <Icon className="h-4 w-4 text-muted-foreground" /> */}
            <Label htmlFor={`${source}-switch`} className="font-medium">
              Enable {title} 
            </Label>
          </div>
      
        </div>
        <Switch
          id={`${source}-switch`}
          checked={config.enabled}
          onCheckedChange={(checked) => {
            onUpdate({ ...config, enabled: checked });
            // Refresh validation errors after toggle change
            setTimeout(refreshValidationErrors, 100);
          }}
        />
      </div>

      {config.enabled && (
        <div className="space-y-4  border-border">
          <div className="space-y-2">
            <Label htmlFor={`${source}-connection-type`}>Connection Type</Label>
            <Select value="http-streaming" disabled>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="http-streaming">HTTP Streaming</SelectItem>
              </SelectContent>
            </Select>
            <div className="text-xs text-muted-foreground">Currently only HTTP Streaming connections are supported</div>
          </div>

          <div className="space-y-2">
            <Label htmlFor={`${source}-endpoint`}>MCP Endpoint URL *</Label>
            <Input
              id={`${source}-endpoint`}
              placeholder="https://api.example.com/mcp"
              value={config.endpointUrl}
              onChange={(e) =>
                onUpdate({ ...config, endpointUrl: e.target.value })
              }
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Additional HTTP Headers</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addHttpHeader}
                className="h-8"
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Header
              </Button>
            </div>

            {config.httpHeaders.length > 0 && (
              <div className="space-y-3 p-3 border border-border rounded-lg bg-surface">
                {config.httpHeaders.map((header, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      placeholder="Header name"
                      value={header.key}
                      onChange={(e) => updateHttpHeader(index, 'key', e.target.value)}
                      className="flex-1"
                    />
                    <Input
                      placeholder="Header value"
                      value={header.value}
                      onChange={(e) => updateHttpHeader(index, 'value', e.target.value)}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeHttpHeader(index)}
                      className="h-9 w-9 p-0 text-muted-foreground hover:text-red-600"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            <div className="text-xs text-muted-foreground">
              Optional. Add HTTP headers for authentication or custom configuration.
            </div>
          </div>

          {/* Test Connection */}
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={onTestConnection}
              disabled={!config.endpointUrl || isTesting}
            >
              {isTesting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Testing...
                </>
              ) : (
                "Test Connection"
              )}
            </Button>

            {testResult === "success" && (
              <div className="flex items-center gap-1 text-green-600">
                <CheckCircle className="h-4 w-4" />
                <span className="text-sm">Connection successful</span>
              </div>
            )}

            {testResult === "error" && (
              <div className="flex items-center gap-1 text-red-600">
                <XCircle className="h-4 w-4" />
                <span className="text-sm">Connection failed</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}