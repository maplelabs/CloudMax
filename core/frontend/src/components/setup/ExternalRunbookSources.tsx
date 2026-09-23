import { Card, CardContent, CardHeader, CardTitle } from "./../ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./../ui/tooltip";
import { HelpCircle } from "lucide-react";
import { MCPConnectionItemModal } from "./MCPConnectionItemModal";
import { SetupConfig } from "./../../types/config";

interface ExternalRunbookSourcesProps {
  externalRunbookConfig: SetupConfig["externalRunbookConfig"];
  onUpdate: (config: SetupConfig["externalRunbookConfig"]) => void;
  onTestConfluence: () => void;
  testingConfluence: boolean;
  confluenceTestResult: "success" | "error" | null;
  refreshValidationErrors: () => void;
}

export function ExternalRunbookSources({
  externalRunbookConfig,
  onUpdate,
  onTestConfluence,
  testingConfluence,
  confluenceTestResult,
  refreshValidationErrors
}: ExternalRunbookSourcesProps) {
  const confluenceConfig = externalRunbookConfig?.confluence || {
    enabled: false,
    base_url: "",
    username: "",
    api_token: ""
  };

  const handleConfluenceUpdate = (config: typeof confluenceConfig) => {
    onUpdate({
      ...externalRunbookConfig,
      confluence: config
    });
  };

  return (
    <Card className="box-shadow mt-8">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          External Runbook Sources
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <HelpCircle className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-white">
                  Configure external sources to import runbooks from documentation platforms
                  like Confluence, Notion, GitHub Wiki, etc.
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Confluence */}
          <MCPConnectionItemModal
            source="confluence"
            config={confluenceConfig}
            onUpdate={handleConfluenceUpdate}
            onTestConnection={onTestConfluence}
            isTesting={testingConfluence}
            testResult={confluenceTestResult}
            refreshValidationErrors={refreshValidationErrors}
          />

          {/* Future: Notion */}
          {/* <MCPConnectionItemModal source="notion" ... /> */}

          {/* Future: GitHub Wiki */}
          {/* <MCPConnectionItemModal source="github-wiki" ... /> */}
        </div>
      </CardContent>
    </Card>
  );
}
