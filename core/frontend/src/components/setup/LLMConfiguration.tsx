import { useState } from "react";
import { Label } from "./../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./../ui/select";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { Eye, EyeOff } from "lucide-react";
import { SetupConfig } from "./../../types/config";

interface LLMConfigurationProps {
  llmConfig: NonNullable<SetupConfig["customDeployment"]>["llm"];
  onUpdate: (llmConfig: NonNullable<SetupConfig["customDeployment"]>["llm"]) => void;
}

export function LLMConfiguration({ llmConfig, onUpdate }: LLMConfigurationProps) {
  const [showLlmApiKey, setShowLlmApiKey] = useState(false);
  const [showAwsApiKey, setShowAwsApiKey] = useState(false);
  const [showAzureAnthropicApiKey, setShowAzureAnthropicApiKey] = useState(false);

  return (
    <div className="space-y-4">
        {/* LLM Provider Selection */}
        <div className="space-y-2">
          <Label htmlFor="llm-provider">LLM Provider *</Label>
          <Select
            value={llmConfig.provider}
            onValueChange={(value: "azure-openai" | "aws-bedrock-claude" | "azure-anthropic") => {
              onUpdate({
                ...llmConfig,
                provider: value,
                // Only create new objects if they don't exist, preserve existing values
                ...(value === "azure-openai" ? {
                  azureOpenAI: llmConfig.azureOpenAI || {
                    apiKey: "",
                    endpointUrl: "",
                    deploymentName: "",
                    apiVersion: "2023-12-01-preview"
                  }
                } : value === "azure-anthropic" ? {
                  azureAnthropic: llmConfig.azureAnthropic || {
                    apiKey: "",
                    endpointUrl: "",
                    modelId: "claude-haiku-4-5"
                  }
                } : {
                  awsBedrock: llmConfig.awsBedrock || {
                    apiKey: "",
                    region: "",
                    modelId: ""
                  }
                })
              });
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select LLM provider" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="azure-openai">Azure OpenAI</SelectItem>
              <SelectItem value="azure-anthropic">Azure Anthropic</SelectItem>
              <SelectItem value="aws-bedrock-claude">AWS Bedrock - Claude</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Azure OpenAI Configuration */}
        {llmConfig.provider === "azure-openai" && llmConfig.azureOpenAI && (
          <div className="space-y-4 pt-4 border-border">
            <div className="space-y-2">
              <Label htmlFor="llm-api-key">API Key *</Label>
              <div className="relative">
                <Input
                  id="llm-api-key"
                  type={showLlmApiKey ? "text" : "password"}
                  placeholder="Enter your Azure OpenAI API key"
                  value={llmConfig.azureOpenAI.apiKey}
                  onChange={(e) =>
                    onUpdate({
                      ...llmConfig,
                      azureOpenAI: {
                        ...llmConfig.azureOpenAI!,
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
                  onClick={() => setShowLlmApiKey(!showLlmApiKey)}
                >
                  {showLlmApiKey ? (
                    <EyeOff className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Eye className="h-4 w-4 text-muted-foreground" />
                  )}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="llm-endpoint">Endpoint URL *</Label>
              <Input
                id="llm-endpoint"
                placeholder="https://your-resource.openai.azure.com/"
                value={llmConfig.azureOpenAI.endpointUrl}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    azureOpenAI: {
                      ...llmConfig.azureOpenAI!,
                      endpointUrl: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="llm-deployment">Deployment Name *</Label>
              <Input
                id="llm-deployment"
                placeholder="gpt-4"
                value={llmConfig.azureOpenAI.deploymentName}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    azureOpenAI: {
                      ...llmConfig.azureOpenAI!,
                      deploymentName: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="llm-api-version">API Version *</Label>
              <Input
                id="llm-api-version"
                placeholder="2023-12-01-preview"
                value={llmConfig.azureOpenAI.apiVersion}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    azureOpenAI: {
                      ...llmConfig.azureOpenAI!,
                      apiVersion: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="pt-4 border-border">
              <div className="text-sm font-medium text-foreground mb-4">Pricing Configuration</div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="llm-price-input">Price per 1K Input Tokens (USD)</Label>
                  <Input
                    id="llm-price-input"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="0.01"
                    value={llmConfig.azureOpenAI.priceUsdPer1kIpTokens ?? ""}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) =>
                      onUpdate({
                        ...llmConfig,
                        azureOpenAI: {
                          ...llmConfig.azureOpenAI!,
                          priceUsdPer1kIpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="llm-price-output">Price per 1K Output Tokens (USD)</Label>
                  <Input
                    id="llm-price-output"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="0.03"
                    value={llmConfig.azureOpenAI.priceUsdPer1kOpTokens ?? ""}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) =>
                      onUpdate({
                        ...llmConfig,
                        azureOpenAI: {
                          ...llmConfig.azureOpenAI!,
                          priceUsdPer1kOpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                        }
                      })
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* AWS Bedrock Configuration */}
        {llmConfig.provider === "aws-bedrock-claude" && llmConfig.awsBedrock && (
          <div className="space-y-4 pt-4 border-border">
            <div className="space-y-2">
              <Label htmlFor="aws-api-key">API Key *</Label>
              <div className="relative">
                <Input
                  id="aws-api-key"
                  type={showAwsApiKey ? "text" : "password"}
                  placeholder="Enter your AWS API key"
                  value={llmConfig.awsBedrock.apiKey}
                  onChange={(e) =>
                    onUpdate({
                      ...llmConfig,
                      awsBedrock: {
                        ...llmConfig.awsBedrock!,
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
                  onClick={() => setShowAwsApiKey(!showAwsApiKey)}
                >
                  {showAwsApiKey ? (
                    <EyeOff className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Eye className="h-4 w-4 text-muted-foreground" />
                  )}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="aws-region">Region *</Label>
              <Input
                id="aws-region"
                placeholder="us-east-1"
                value={llmConfig.awsBedrock.region}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    awsBedrock: {
                      ...llmConfig.awsBedrock!,
                      region: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="aws-model-id">Model ID *</Label>
              <Input
                id="aws-model-id"
                placeholder="anthropic.claude-v2"
                value={llmConfig.awsBedrock.modelId}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    awsBedrock: {
                      ...llmConfig.awsBedrock!,
                      modelId: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="pt-4 border-border">
              <div className="text-sm font-medium text-foreground mb-4">Pricing Configuration</div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="aws-price-input">Price per 1K Input Tokens (USD)</Label>
                  <Input
                    id="aws-price-input"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="0.01"
                    value={llmConfig.awsBedrock.priceUsdPer1kIpTokens ?? ""}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) =>
                      onUpdate({
                        ...llmConfig,
                        awsBedrock: {
                          ...llmConfig.awsBedrock!,
                          priceUsdPer1kIpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="aws-price-output">Price per 1K Output Tokens (USD)</Label>
                  <Input
                    id="aws-price-output"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="0.03"
                    value={llmConfig.awsBedrock.priceUsdPer1kOpTokens ?? ""}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) =>
                      onUpdate({
                        ...llmConfig,
                        awsBedrock: {
                          ...llmConfig.awsBedrock!,
                          priceUsdPer1kOpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                        }
                      })
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Azure Anthropic Configuration */}
        {llmConfig.provider === "azure-anthropic" && llmConfig.azureAnthropic && (
          <div className="space-y-4 pt-4 border-border">
            <div className="space-y-2">
              <Label htmlFor="azure-anthropic-endpoint">Endpoint URL *</Label>
              <Input
                id="azure-anthropic-endpoint"
                placeholder="https://your-resource.services.ai.azure.com/anthropic/v1/messages"
                value={llmConfig.azureAnthropic.endpointUrl}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    azureAnthropic: {
                      ...llmConfig.azureAnthropic!,
                      endpointUrl: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="azure-anthropic-api-key">API Key *</Label>
              <div className="relative">
                <Input
                  id="azure-anthropic-api-key"
                  type={showAzureAnthropicApiKey ? "text" : "password"}
                  placeholder="Enter your Azure API key"
                  value={llmConfig.azureAnthropic.apiKey}
                  onChange={(e) =>
                    onUpdate({
                      ...llmConfig,
                      azureAnthropic: {
                        ...llmConfig.azureAnthropic!,
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
                  onClick={() => setShowAzureAnthropicApiKey(!showAzureAnthropicApiKey)}
                >
                  {showAzureAnthropicApiKey ? (
                    <EyeOff className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Eye className="h-4 w-4 text-muted-foreground" />
                  )}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="azure-anthropic-model-id">Model ID *</Label>
              <Input
                id="azure-anthropic-model-id"
                placeholder="claude-haiku-4-5"
                value={llmConfig.azureAnthropic.modelId}
                onChange={(e) =>
                  onUpdate({
                    ...llmConfig,
                    azureAnthropic: {
                      ...llmConfig.azureAnthropic!,
                      modelId: e.target.value
                    }
                  })
                }
              />
            </div>

            <div className="pt-4 border-border">
              <div className="text-sm font-medium text-foreground mb-4">Pricing Configuration</div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="azure-anthropic-price-input">Price per 1K Input Tokens (USD)</Label>
                  <Input
                    id="azure-anthropic-price-input"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="0.01"
                    value={llmConfig.azureAnthropic.priceUsdPer1kIpTokens ?? ""}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) =>
                      onUpdate({
                        ...llmConfig,
                        azureAnthropic: {
                          ...llmConfig.azureAnthropic!,
                          priceUsdPer1kIpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="azure-anthropic-price-output">Price per 1K Output Tokens (USD)</Label>
                  <Input
                    id="azure-anthropic-price-output"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="0.03"
                    value={llmConfig.azureAnthropic.priceUsdPer1kOpTokens ?? ""}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) =>
                      onUpdate({
                        ...llmConfig,
                        azureAnthropic: {
                          ...llmConfig.azureAnthropic!,
                          priceUsdPer1kOpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                        }
                      })
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
  );
}
