import { useState } from "react";
import { Label } from "./../ui/label";
import { Switch } from "./../ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./../ui/select";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { Eye, EyeOff } from "lucide-react";
import { SetupConfig } from "./../../types/config";


interface SecondaryLLMConfigurationProps {
  secondaryLlmConfig: NonNullable<SetupConfig["customDeployment"]>["secondaryLlm"];
  onUpdate: (secondaryLlmConfig: NonNullable<SetupConfig["customDeployment"]>["secondaryLlm"]) => void;
}
export function SecondaryLLMConfiguration({ secondaryLlmConfig, onUpdate }: SecondaryLLMConfigurationProps) {
  const [showSecondaryLlmApiKey, setShowSecondaryLlmApiKey] = useState(false);
  const [showSecondaryAwsApiKey, setShowSecondaryAwsApiKey] = useState(false);
  const [showSecondaryAzureAnthropicApiKey, setShowSecondaryAzureAnthropicApiKey] = useState(false);

  return (
    <div className="space-y-4">
        {/* Enable Secondary LLM Switch */}
        <div className="flex items-center justify-between p-4 border border-border rounded-lg bg-surface">
          <div className="space-y-1">
            <Label htmlFor="enable-secondary-llm" className="font-medium">
              Enable Secondary LLM
            </Label>
          </div>
          <Switch
            id="enable-secondary-llm"
            checked={!secondaryLlmConfig.sameAsPrimary}
            onCheckedChange={(checked) => {
              onUpdate({
                ...secondaryLlmConfig,
                sameAsPrimary: !checked,
                // Initialize provider and configs when switching to custom
                provider: checked ? (secondaryLlmConfig.provider || "azure-openai") : undefined,
                azureOpenAI: checked && !secondaryLlmConfig.azureOpenAI ? {
                  apiKey: "",
                  endpointUrl: "",
                  deploymentName: "",
                  apiVersion: "2023-12-01-preview"
                } : secondaryLlmConfig.azureOpenAI,
              });
            }}
          />
        </div>

        {/* Secondary LLM Configuration - shown when secondary LLM is enabled */}
        {!secondaryLlmConfig.sameAsPrimary && (
          <div className="space-y-4 pt-4">
            {/* LLM Provider Selection */}
            <div className="space-y-2">
              <Label htmlFor="secondary-llm-provider">Secondary LLM Provider *</Label>
              <Select
                value={secondaryLlmConfig.provider || "azure-openai"}
                onValueChange={(value: "azure-openai" | "aws-bedrock-claude" | "azure-anthropic") => {
                  onUpdate({
                    ...secondaryLlmConfig,
                    provider: value,
                    // Only create new objects if they don't exist, preserve existing values
                    ...(value === "azure-openai" ? {
                      azureOpenAI: secondaryLlmConfig.azureOpenAI || {
                        apiKey: "",
                        endpointUrl: "",
                        deploymentName: "",
                        apiVersion: "2023-12-01-preview"
                      }
                    } : value === "azure-anthropic" ? {
                      azureAnthropic: secondaryLlmConfig.azureAnthropic || {
                        apiKey: "",
                        endpointUrl: "",
                        modelId: "claude-haiku-4-5"
                      }
                    } : {
                      awsBedrock: secondaryLlmConfig.awsBedrock || {
                        apiKey: "",
                        region: "",
                        modelId: ""
                      }
                    })
                  });
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select secondary LLM provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="azure-openai">Azure OpenAI</SelectItem>
                  <SelectItem value="azure-anthropic">Azure Anthropic</SelectItem>
                  <SelectItem value="aws-bedrock-claude">AWS Bedrock - Claude</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Azure OpenAI Configuration */}
            {secondaryLlmConfig.provider === "azure-openai" && secondaryLlmConfig.azureOpenAI && (
              <div className="space-y-4 pt-4 border-border">
                <div className="space-y-2">
                  <Label htmlFor="secondary-llm-api-key">API Key *</Label>
                  <div className="relative">
                    <Input
                      id="secondary-llm-api-key"
                      type={showSecondaryLlmApiKey ? "text" : "password"}
                      placeholder="Enter your Azure OpenAI API key"
                      value={secondaryLlmConfig.azureOpenAI.apiKey}
                      onChange={(e) =>
                        onUpdate({
                          ...secondaryLlmConfig,
                          azureOpenAI: {
                            ...secondaryLlmConfig.azureOpenAI!,
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
                      onClick={() => setShowSecondaryLlmApiKey(!showSecondaryLlmApiKey)}
                    >
                      {showSecondaryLlmApiKey ? (
                        <EyeOff className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <Eye className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-llm-endpoint">Endpoint URL *</Label>
                  <Input
                    id="secondary-llm-endpoint"
                    placeholder="https://your-resource.openai.azure.com/"
                    value={secondaryLlmConfig.azureOpenAI.endpointUrl}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        azureOpenAI: {
                          ...secondaryLlmConfig.azureOpenAI!,
                          endpointUrl: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-llm-deployment">Deployment Name *</Label>
                  <Input
                    id="secondary-llm-deployment"
                    placeholder="gpt-4"
                    value={secondaryLlmConfig.azureOpenAI.deploymentName}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        azureOpenAI: {
                          ...secondaryLlmConfig.azureOpenAI!,
                          deploymentName: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-llm-api-version">API Version *</Label>
                  <Input
                    id="secondary-llm-api-version"
                    placeholder="2023-12-01-preview"
                    value={secondaryLlmConfig.azureOpenAI.apiVersion}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        azureOpenAI: {
                          ...secondaryLlmConfig.azureOpenAI!,
                          apiVersion: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="pt-4  border-border">
                  <div className="text-sm font-medium text-foreground mb-4">Pricing Configuration</div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="secondary-llm-price-input">Price per 1K Input Tokens (USD)</Label>
                      <Input
                        id="secondary-llm-price-input"
                        type="number"
                        step="0.0001"
                        min="0"
                        placeholder="0.01"
                        value={secondaryLlmConfig.azureOpenAI.priceUsdPer1kIpTokens ?? ""}
                        onWheel={(e) => e.currentTarget.blur()}
                        onChange={(e) =>
                          onUpdate({
                            ...secondaryLlmConfig,
                            azureOpenAI: {
                              ...secondaryLlmConfig.azureOpenAI!,
                              priceUsdPer1kIpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                            }
                          })
                        }
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="secondary-llm-price-output">Price per 1K Output Tokens (USD)</Label>
                      <Input
                        id="secondary-llm-price-output"
                        type="number"
                        step="0.0001"
                        min="0"
                        placeholder="0.03"
                        value={secondaryLlmConfig.azureOpenAI.priceUsdPer1kOpTokens ?? ""}
                        onWheel={(e) => e.currentTarget.blur()}
                        onChange={(e) =>
                          onUpdate({
                            ...secondaryLlmConfig,
                            azureOpenAI: {
                              ...secondaryLlmConfig.azureOpenAI!,
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
            {secondaryLlmConfig.provider === "aws-bedrock-claude" && secondaryLlmConfig.awsBedrock && (
              <div className="space-y-4 pt-4 border-border">
                <div className="space-y-2">
                  <Label htmlFor="secondary-aws-api-key">API Key *</Label>
                  <div className="relative">
                    <Input
                      id="secondary-aws-api-key"
                      type={showSecondaryAwsApiKey ? "text" : "password"}
                      placeholder="Enter your AWS API key"
                      value={secondaryLlmConfig.awsBedrock.apiKey}
                      onChange={(e) =>
                        onUpdate({
                          ...secondaryLlmConfig,
                          awsBedrock: {
                            ...secondaryLlmConfig.awsBedrock!,
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
                      onClick={() => setShowSecondaryAwsApiKey(!showSecondaryAwsApiKey)}
                    >
                      {showSecondaryAwsApiKey ? (
                        <EyeOff className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <Eye className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-aws-region">Region *</Label>
                  <Input
                    id="secondary-aws-region"
                    placeholder="us-east-1"
                    value={secondaryLlmConfig.awsBedrock.region}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        awsBedrock: {
                          ...secondaryLlmConfig.awsBedrock!,
                          region: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-aws-model-id">Model ID *</Label>
                  <Input
                    id="secondary-aws-model-id"
                    placeholder="anthropic.claude-v2"
                    value={secondaryLlmConfig.awsBedrock.modelId}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        awsBedrock: {
                          ...secondaryLlmConfig.awsBedrock!,
                          modelId: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="pt-4  border-border">
                  <div className="text-sm font-medium text-foreground mb-4">Pricing Configuration</div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="secondary-aws-price-input">Price per 1K Input Tokens (USD)</Label>
                      <Input
                        id="secondary-aws-price-input"
                        type="number"
                        step="0.0001"
                        min="0"
                        placeholder="0.01"
                        value={secondaryLlmConfig.awsBedrock.priceUsdPer1kIpTokens ?? ""}
                        onWheel={(e) => e.currentTarget.blur()}
                        onChange={(e) =>
                          onUpdate({
                            ...secondaryLlmConfig,
                            awsBedrock: {
                              ...secondaryLlmConfig.awsBedrock!,
                              priceUsdPer1kIpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                            }
                          })
                        }
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="secondary-aws-price-output">Price per 1K Output Tokens (USD)</Label>
                      <Input
                        id="secondary-aws-price-output"
                        type="number"
                        step="0.0001"
                        min="0"
                        placeholder="0.03"
                        value={secondaryLlmConfig.awsBedrock.priceUsdPer1kOpTokens ?? ""}
                        onWheel={(e) => e.currentTarget.blur()}
                        onChange={(e) =>
                          onUpdate({
                            ...secondaryLlmConfig,
                            awsBedrock: {
                              ...secondaryLlmConfig.awsBedrock!,
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
            {secondaryLlmConfig.provider === "azure-anthropic" && secondaryLlmConfig.azureAnthropic && (
              <div className="space-y-4 pt-4 border-border">
                <div className="space-y-2">
                  <Label htmlFor="secondary-azure-anthropic-endpoint">Endpoint URL *</Label>
                  <Input
                    id="secondary-azure-anthropic-endpoint"
                    placeholder="https://your-resource.services.ai.azure.com/anthropic/v1/messages"
                    value={secondaryLlmConfig.azureAnthropic.endpointUrl}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        azureAnthropic: {
                          ...secondaryLlmConfig.azureAnthropic!,
                          endpointUrl: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-azure-anthropic-api-key">API Key *</Label>
                  <div className="relative">
                    <Input
                      id="secondary-azure-anthropic-api-key"
                      type={showSecondaryAzureAnthropicApiKey ? "text" : "password"}
                      placeholder="Enter your Azure API key"
                      value={secondaryLlmConfig.azureAnthropic.apiKey}
                      onChange={(e) =>
                        onUpdate({
                          ...secondaryLlmConfig,
                          azureAnthropic: {
                            ...secondaryLlmConfig.azureAnthropic!,
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
                      onClick={() => setShowSecondaryAzureAnthropicApiKey(!showSecondaryAzureAnthropicApiKey)}
                    >
                      {showSecondaryAzureAnthropicApiKey ? (
                        <EyeOff className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <Eye className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="secondary-azure-anthropic-model-id">Model ID *</Label>
                  <Input
                    id="secondary-azure-anthropic-model-id"
                    placeholder="claude-haiku-4-5"
                    value={secondaryLlmConfig.azureAnthropic.modelId}
                    onChange={(e) =>
                      onUpdate({
                        ...secondaryLlmConfig,
                        azureAnthropic: {
                          ...secondaryLlmConfig.azureAnthropic!,
                          modelId: e.target.value
                        }
                      })
                    }
                  />
                </div>

                <div className="pt-4  border-border">
                  <div className="text-sm font-medium text-foreground mb-4">Pricing Configuration</div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="secondary-azure-anthropic-price-input">Price per 1K Input Tokens (USD)</Label>
                      <Input
                        id="secondary-azure-anthropic-price-input"
                        type="number"
                        step="0.0001"
                        min="0"
                        placeholder="0.01"
                        value={secondaryLlmConfig.azureAnthropic.priceUsdPer1kIpTokens ?? ""}
                        onWheel={(e) => e.currentTarget.blur()}
                        onChange={(e) =>
                          onUpdate({
                            ...secondaryLlmConfig,
                            azureAnthropic: {
                              ...secondaryLlmConfig.azureAnthropic!,
                              priceUsdPer1kIpTokens: e.target.value ? parseFloat(e.target.value) : undefined
                            }
                          })
                        }
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="secondary-azure-anthropic-price-output">Price per 1K Output Tokens (USD)</Label>
                      <Input
                        id="secondary-azure-anthropic-price-output"
                        type="number"
                        step="0.0001"
                        min="0"
                        placeholder="0.03"
                        value={secondaryLlmConfig.azureAnthropic.priceUsdPer1kOpTokens ?? ""}
                        onWheel={(e) => e.currentTarget.blur()}
                        onChange={(e) =>
                          onUpdate({
                            ...secondaryLlmConfig,
                            azureAnthropic: {
                              ...secondaryLlmConfig.azureAnthropic!,
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
        )}
      </div>
  );
}
