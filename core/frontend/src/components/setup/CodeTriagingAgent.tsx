import { Card, CardContent, CardHeader, CardTitle } from "./../ui/card";
import { Label } from "./../ui/label";
import { Switch } from "./../ui/switch";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { SetupConfig } from "./../../types/config";
import { Loader2, CheckCircle, XCircle } from "lucide-react";

interface CodeTriagingAgentProps {
  codeTriaging: SetupConfig["codeTriaging"];
  onUpdate: (codeTriaging: SetupConfig["codeTriaging"]) => void;
  refreshValidationErrors: () => void;
  onTestConnection?: () => Promise<void>;
  isTesting?: boolean;
  testResult?: "success" | "error" | null;
}

export function CodeTriagingAgent({
  codeTriaging,
  onUpdate,
  refreshValidationErrors,
  onTestConnection,
  isTesting = false,
  testResult = null
}: CodeTriagingAgentProps) {

  return (
    <Card className="box-shadow">
      <CardHeader>
        <CardTitle className="font-bold" style={{fontSize:"18px"}}>Code Triaging Agent</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-sm text-muted-foreground mb-4">
          Configure the AI agent responsible for analyzing code-related alerts and identifying root causes in your repository.
        </div>

        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <Label htmlFor="triaging-switch" className="font-medium text-foreground">
              Enable Code Triaging Agent
            </Label>
            <div className="text-sm text-muted-foreground">
              Automatically analyze application errors using GitHub repository code
            </div>
          </div>
          <Switch
            id="triaging-switch"
            checked={codeTriaging.enabled}
            onCheckedChange={(checked) => {
              onUpdate({ ...codeTriaging, enabled: checked });
              // Refresh validation errors after toggle change
              setTimeout(refreshValidationErrors, 100);
            }}
          />
        </div>

        {codeTriaging.enabled && (
          <div className="ml-6 space-y-4 border-l border-border pl-4">
            <div className="space-y-2">
              <Label htmlFor="code-triage-base-url">Service Base URL *</Label>
              <Input
                id="code-triage-base-url"
                placeholder="http://code-triage-agent:8002"
                value={codeTriaging.baseUrl}
                onChange={(e) =>
                  onUpdate({ ...codeTriaging, baseUrl: e.target.value })
                }
              />
              <p className="text-xs text-muted-foreground">
                URL of the code-triage-agent service (e.g., http://code-triage-agent:8002)
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="timeout-seconds">Timeout (seconds) *</Label>
                <Input
                  id="timeout-seconds"
                  type="number"
                  min="1"
                  max="300"
                  placeholder="30"
                  value={codeTriaging.timeoutSeconds === 0 ? '' : (codeTriaging.timeoutSeconds || '')}
                  onChange={(e) => {
                    const val = e.target.value;
                    // Allow empty string temporarily, or parse the number
                    const numValue = val === '' ? 0 : parseInt(val);
                    onUpdate({ ...codeTriaging, timeoutSeconds: numValue });
                  }}
                  onBlur={(e) => {
                    // On blur, if empty or 0, set to default
                    if (!e.target.value || parseInt(e.target.value) === 0) {
                      onUpdate({ ...codeTriaging, timeoutSeconds: 30 });
                    }
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  Request timeout (1-300 seconds)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="max-retries">Max Retries *</Label>
                <Input
                  id="max-retries"
                  type="number"
                  min="0"
                  max="10"
                  placeholder="3"
                  value={codeTriaging.maxRetries === -1 ? '' : (codeTriaging.maxRetries ?? '')}
                  onChange={(e) => {
                    const val = e.target.value;
                    // Allow empty string temporarily, or parse the number (allow 0)
                    const numValue = val === '' ? -1 : parseInt(val);
                    onUpdate({ ...codeTriaging, maxRetries: numValue });
                  }}
                  onBlur={(e) => {
                    // On blur, if empty or -1, set to default
                    const currentVal = e.target.value === '' ? -1 : parseInt(e.target.value);
                    if (currentVal < 0) {
                      onUpdate({ ...codeTriaging, maxRetries: 3 });
                    }
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  Retry attempts (0-10)
                </p>
              </div>
            </div>

            {/* Test Connection */}
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                onClick={onTestConnection}
                disabled={!codeTriaging.baseUrl || isTesting}
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

            <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-md p-3">
              <p className="text-sm text-blue-900 dark:text-blue-200">
                <strong>Note:</strong> The code triaging agent requires GitHub access configured via environment variables in the code-triage-agent service (GITHUB_TOKEN).
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}