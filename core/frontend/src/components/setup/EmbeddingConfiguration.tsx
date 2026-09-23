import { useState } from "react";
import { Label } from "./../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./../ui/select";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { Eye, EyeOff } from "lucide-react";
import { SetupConfig } from "./../../types/config";

interface EmbeddingConfigurationProps {
  embeddingConfig: NonNullable<SetupConfig["customDeployment"]>["embedding"];
  onUpdate: (embeddingConfig: NonNullable<SetupConfig["customDeployment"]>["embedding"]) => void;
}

export function EmbeddingConfiguration({ embeddingConfig, onUpdate }: EmbeddingConfigurationProps) {
  const [showEmbeddingApiKey, setShowEmbeddingApiKey] = useState(false);

  return (
    <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="embedding-provider">Embedding Model Provider</Label>
          <Select value="azure-openai" disabled>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="azure-openai">Azure OpenAI</SelectItem>
            </SelectContent>
          </Select>
          <div className="text-xs text-muted-foreground">Currently only Azure OpenAI is supported</div>
        </div>

        <div className="space-y-4 pt-4 border-border">
          <div className="space-y-2">
            <Label htmlFor="embedding-api-key">API Key *</Label>
            <div className="relative">
              <Input
                id="embedding-api-key"
                type={showEmbeddingApiKey ? "text" : "password"}
                placeholder="Enter your Azure OpenAI API key"
                value={embeddingConfig.azureOpenAI.apiKey}
                onChange={(e) =>
                  onUpdate({
                    ...embeddingConfig,
                    azureOpenAI: {
                      ...embeddingConfig.azureOpenAI,
                      apiKey: e.target.value
                    }
                  })
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                onClick={() => setShowEmbeddingApiKey(!showEmbeddingApiKey)}
              >
                {showEmbeddingApiKey ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="embedding-endpoint">Endpoint URL *</Label>
            <Input
              id="embedding-endpoint"
              placeholder="https://your-resource.openai.azure.com/"
              value={embeddingConfig.azureOpenAI.endpointUrl}
              onChange={(e) =>
                onUpdate({
                  ...embeddingConfig,
                  azureOpenAI: {
                    ...embeddingConfig.azureOpenAI,
                    endpointUrl: e.target.value
                  }
                })
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="embedding-deployment">Deployment Name *</Label>
            <Input
              id="embedding-deployment"
              placeholder="text-embedding-ada-002"
              value={embeddingConfig.azureOpenAI.deploymentName}
              onChange={(e) =>
                onUpdate({
                  ...embeddingConfig,
                  azureOpenAI: {
                    ...embeddingConfig.azureOpenAI,
                    deploymentName: e.target.value
                  }
                })
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="embedding-api-version">API Version *</Label>
            <Input
              id="embedding-api-version"
              placeholder="2023-12-01-preview"
              value={embeddingConfig.azureOpenAI.apiVersion}
              onChange={(e) =>
                onUpdate({
                  ...embeddingConfig,
                  azureOpenAI: {
                    ...embeddingConfig.azureOpenAI,
                    apiVersion: e.target.value
                  }
                })
              }
            />
          </div>
        </div>
      </div>
  );
}
