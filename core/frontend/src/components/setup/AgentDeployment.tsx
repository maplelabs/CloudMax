import { RadioGroup, RadioGroupItem } from "./../ui/radio-group";
import { Label } from "./../ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "./../ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./../ui/tooltip";
import { HelpCircle } from "lucide-react";
import { cn } from "./../ui/utils";
import { LLMConfigurationModal } from "./LLMConfigurationModal";
import { SecondaryLLMConfigurationModal } from "./SecondaryLLMConfigurationModal";
import { EmbeddingConfigurationModal } from "./EmbeddingConfigurationModal";
import { SetupConfig } from "./../../types/config";

interface AgentDeploymentProps {
  deployment: "custom" | "azure";
  customDeployment?: SetupConfig["customDeployment"];
  onDeploymentChange: (value: "custom" | "azure") => void;
  onConfigUpdate: (config: SetupConfig["customDeployment"]) => void;
  refreshValidationErrors: () => void;
}

export function AgentDeployment({
  deployment,
  customDeployment,
  onDeploymentChange,
  onConfigUpdate,
  refreshValidationErrors
}: AgentDeploymentProps) {
  return (
    <>
      <Card className="box-shadow">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Agent Deployment
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <HelpCircle className="h-4 w-4 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>Choose how agents are deployed and managed</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted-foreground mb-4">
            Select one deployment method for your agents.
          </div>

          <RadioGroup
            value={deployment}
            onValueChange={(value: "custom" | "azure") => {
              onDeploymentChange(value);
              // Refresh validation errors after deployment change
              setTimeout(refreshValidationErrors, 100);
            }}
            className="grid grid-cols-2 gap-4"
          >
            <div className={cn(
              "relative border-2 rounded-sm p-4 transition-all duration-200 cursor-pointer",
              "hover:shadow-sm",
              deployment === "custom"
                ? "shadow-sm border-primary"
                : "border-border bg-card hover:bg-surface-hover"
            )}
              onClick={() => onDeploymentChange("custom")}
              style={{ background: "#edfff6" }}
            >
              <div className="flex items-start space-x-3">
                <RadioGroupItem value="custom" id="custom-deployment" className="mt-0.5" />
                <div className="flex-1">
                  <Label htmlFor="custom-deployment" className={cn(
                    "font-medium cursor-pointer",
                    deployment === "custom" ? "text-success-text" : "text-foreground"
                  )}>
                    Custom Deployment
                  </Label>
                  <div className={cn(
                    "text-sm mt-1",
                    deployment === "custom" ? "text-success-text" : "text-muted-foreground"
                  )}>
                    Deploy and manage agents using your own infrastructure
                  </div>
                </div>
              </div>
            </div>

            <div className={cn(
              "relative border-2 rounded-md p-4 transition-all duration-200 cursor-pointer",
              "hover:shadow-sm",
              deployment === "azure"
                ? "border-primary bg-success-light shadow-sm"
                : "border-border bg-card hover:bg-surface-hover"
            )}
              onClick={() => onDeploymentChange("azure")}
            >
              <div className="flex items-start space-x-3">
                <RadioGroupItem value="azure" id="azure-deployment" className="mt-0.5" />
                <div className="flex-1">
                  <Label htmlFor="azure-deployment" className={cn(
                    "font-medium cursor-pointer",
                    deployment === "azure" ? "text-success-text" : "text-foreground"
                  )}>
                    Azure Agent Foundry
                  </Label>
                  <div className={cn(
                    "text-sm mt-1",
                    deployment === "azure" ? "text-success-text" : "text-muted-foreground"
                  )}>
                    Use Microsoft Azure's managed agent infrastructure
                  </div>
                </div>
              </div>
            </div>
          </RadioGroup>
        </CardContent>
      </Card>


      {/* Custom Deployment Configuration - shown when Custom is selected */}
      {deployment === "custom" && customDeployment && (
        <Card className="box-shadow">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Model Configuration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-1 lg:grid-cols-3 gap-4">
              <LLMConfigurationModal
                llmConfig={customDeployment.llm}
                onUpdate={(llm: NonNullable<SetupConfig["customDeployment"]>["llm"]) => onConfigUpdate({ ...customDeployment, llm })}
              />
              <SecondaryLLMConfigurationModal
                secondaryLlmConfig={customDeployment.secondaryLlm}
                onUpdate={(secondaryLlm: NonNullable<SetupConfig["customDeployment"]>["secondaryLlm"]) => onConfigUpdate({ ...customDeployment, secondaryLlm })}
              />
              <EmbeddingConfigurationModal
                embeddingConfig={customDeployment.embedding}
                onUpdate={(embedding: NonNullable<SetupConfig["customDeployment"]>["embedding"]) => onConfigUpdate({ ...customDeployment, embedding })}
              />
            </div>
          </CardContent>
        </Card>
      )}

    </>
  );
}