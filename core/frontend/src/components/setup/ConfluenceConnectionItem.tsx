import { Label } from "./../ui/label";
import { Switch } from "./../ui/switch";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { BookOpen, CheckCircle, XCircle, Loader2 } from "lucide-react";

interface ConfluenceConnectionItemProps {
  config: {
    enabled: boolean;
    base_url: string;
    username: string;
    api_token: string;
  };
  onUpdate: (config: {
    enabled: boolean;
    base_url: string;
    username: string;
    api_token: string;
  }) => void;
  onTestConnection: () => void;
  isTesting: boolean;
  testResult: "success" | "error" | null;
  refreshValidationErrors: () => void;
}

export function ConfluenceConnectionItem({
  config,
  onUpdate,
  onTestConnection,
  isTesting,
  testResult,
  refreshValidationErrors
}: ConfluenceConnectionItemProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg flex items-center justify-between bg-surface-secondary p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label htmlFor="confluence-switch" className="font-medium">
              Enable Confluence Integration
            </Label>
          </div>
        </div>
        <Switch
          id="confluence-switch"
          checked={config.enabled}
          onCheckedChange={(checked) => {
            onUpdate({ ...config, enabled: checked });
            setTimeout(refreshValidationErrors, 100);
          }}
        />
      </div>

      {config.enabled && (
        <div className="space-y-4 border-border">
          <div className="space-y-2">
            <Label htmlFor="confluence-base-url">Confluence Base URL *</Label>
            <Input
              id="confluence-base-url"
              placeholder="https://your-company.atlassian.net"
              value={config.base_url}
              onChange={(e) =>
                onUpdate({ ...config, base_url: e.target.value })
              }
            />
            <div className="text-xs text-muted-foreground">
              Your Confluence instance URL (e.g., https://company.atlassian.net)
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="confluence-username">Username/Email *</Label>
            <Input
              id="confluence-username"
              type="email"
              placeholder="user@company.com"
              value={config.username}
              onChange={(e) =>
                onUpdate({ ...config, username: e.target.value })
              }
            />
            <div className="text-xs text-muted-foreground">
              Your Confluence account email address
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="confluence-api-token">API Token *</Label>
            <Input
              id="confluence-api-token"
              type="password"
              placeholder="Enter your Confluence API token"
              value={config.api_token}
              onChange={(e) =>
                onUpdate({ ...config, api_token: e.target.value })
              }
            />
            <div className="text-xs text-muted-foreground">
              Generate an API token from{" "}
              <a
                href="https://id.atlassian.com/manage-profile/security/api-tokens"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                Atlassian Account Settings
              </a>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onTestConnection}
              disabled={isTesting || !config.base_url || !config.username || !config.api_token}
              className="gap-2"
            >
              {isTesting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Testing Connection...
                </>
              ) : (
                <>
                  <BookOpen className="h-4 w-4" />
                  Test Connection
                </>
              )}
            </Button>

            {testResult === "success" && (
              <div className="flex items-center gap-1 text-sm text-emerald-700">
                <CheckCircle className="h-4 w-4" />
                <span>Connection successful!</span>
              </div>
            )}

            {testResult === "error" && (
              <div className="flex items-center gap-1 text-sm text-danger">
                <XCircle className="h-4 w-4" />
                <span>Connection failed. Please check your credentials.</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
