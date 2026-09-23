import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useConfig, useCreateConfig, useUpdateConfig, useTestConnection } from "../../hooks/useConfig";
import { SetupConfig, TestConnectionRequest } from "../../types/config";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { Loader2, AlertTriangle, AlertCircle } from "lucide-react";
import { cn } from "../ui/utils";
import { toast } from "sonner";
import { generateConfigHash, mapApiToComponentConfig, mapComponentToApiConfig } from "../setup/utils";
import { AlertTriageLevels } from "../setup/AlertTriageLevels";
import { AgentDeployment } from "../setup/AgentDeployment";
import { MCPConnections } from "../setup/MCPConnections";
import { ExternalRunbookSources } from "../setup/ExternalRunbookSources";
import { CodeTriagingAgent } from "../setup/CodeTriagingAgent";
import { ValidationErrors } from "../setup/ValidationErrors";
import { ChaosSystemToggle } from "../setup/ChaosSystemToggle";
import { AutomaticTriageToggle } from "../setup/AutomaticTriageToggle";
import { AlertGroupingToggle } from "../setup/AlertGroupingToggle";
import apiClient from "../../service/api";
import { Card } from "../ui/card";

export function Setup() {
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState("general");

  const { config: apiConfig, isLoading, isError, error,refetch } = useConfig();
  const createConfigMutation = useCreateConfig();
  const updateConfigMutation = useUpdateConfig();
  const testConnectionMutation = useTestConnection();

  const [config, setConfig] = useState<SetupConfig | null>(null);
  const [originalConfigHash, setOriginalConfigHash] = useState<string>("");
  const [isDefaultConfig, setIsDefaultConfig] = useState<boolean>(false);

  // Update active tab when URL parameter changes
  useEffect(() => {
    if (tabParam) {
      setActiveTab(tabParam);
    } else {
      setActiveTab("general");
    }
  }, [tabParam]);

  useEffect(() => {
    if (apiConfig) {
      const componentConfig = mapApiToComponentConfig(apiConfig);
      const hash = generateConfigHash(componentConfig);
      setConfig(componentConfig);
      setOriginalConfigHash(hash);
      setIsDefaultConfig(apiConfig.default_config === true);
      // Reset unsaved changes flag when loading new config
      setHasUnsavedChanges(false);
    }
  }, [apiConfig]);

  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [testingMcpConnections, setTestingMcpConnections] = useState<{ grafana: boolean; jaeger: boolean; opensearch: boolean }>({
    grafana: false,
    jaeger: false,
    opensearch: false
  });
  const [mcpConnectionTestResults, setMcpConnectionTestResults] = useState<{
    grafana: "success" | "error" | null;
    jaeger: "success" | "error" | null;
    opensearch: "success" | "error" | null;
  }>({
    grafana: null,
    jaeger: null,
    opensearch: null
  });
  const [testingDiagnosticConnections, setTestingDiagnosticConnections] = useState<{ [key: number]: boolean }>({});
  const [diagnosticConnectionTestResults, setDiagnosticConnectionTestResults] = useState<{ [key: number]: "success" | "error" | null }>({});
  const [testingCodeTriageAgent, setTestingCodeTriageAgent] = useState(false);
  const [codeTriageTestResult, setCodeTriageTestResult] = useState<"success" | "error" | null>(null);
  const [testingConfluence, setTestingConfluence] = useState(false);
  const [confluenceTestResult, setConfluenceTestResult] = useState<"success" | "error" | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showValidationErrors, setShowValidationErrors] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  useEffect(() => {
    if (!config || !originalConfigHash) {
      setHasUnsavedChanges(false);
      return;
    }

    // Debounce the hash comparison to avoid showing unsaved for temporary states
    const timeoutId = setTimeout(() => {
      const currentHash = generateConfigHash(config);
      const hasChanges = currentHash !== originalConfigHash;
      setHasUnsavedChanges(hasChanges);
    }, 500); // 500ms delay

    return () => clearTimeout(timeoutId);
  }, [config, originalConfigHash]);

  // Separate effect for validation error updates with debouncing
  useEffect(() => {
    if (showValidationErrors && config) {
      const timeoutId = setTimeout(() => {
        const currentErrors = getValidationErrors();
        setValidationErrors(currentErrors);

        // Hide validation errors if all errors are resolved
        if (currentErrors.length === 0) {
          setShowValidationErrors(false);
        }
      }, 300); // 300ms debounce for validation updates

      return () => clearTimeout(timeoutId);
    }
  }, [config, showValidationErrors]);

  // Handle triage level updates
  const updateTriageLevels = (level: "p1" | "p2" | "p3", enabled: boolean) => {
    setConfig((prev: any) => ({
      ...prev,
      triageLevels: {
        ...prev.triageLevels,
        [level]: enabled
      }
    }));
  };

  const handleSave = async () => {
    if (!config) return;

    // Check for validation errors
    const errors = getValidationErrors();
    if (errors.length > 0) {
      setValidationErrors(errors);
      setShowValidationErrors(true);
      // Scroll to validation errors
      setTimeout(() => {
        const errorElement = document.querySelector('[data-validation-errors]');
        if (errorElement) {
          errorElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
      return;
    }

    // Clear any existing validation errors
    setShowValidationErrors(false);
    setValidationErrors([]);

    setIsSaving(true);
    try {
      const apiPayload = mapComponentToApiConfig(config);

      if (isDefaultConfig) {
        // Use POST call for default config
        await createConfigMutation.mutateAsync(apiPayload);
        setIsDefaultConfig(false); // After first save, it's no longer default config
      } else {
        // Use PUT call for existing config
        await updateConfigMutation.mutateAsync(apiPayload);
      }

      // Update original hash after successful save
      setOriginalConfigHash(generateConfigHash(config));

      // Show success toast
      toast.success("Settings saved successfully!");
    } catch (error) {
      console.error("Failed to save settings:", error);

      // Show error toast
      toast.error("Failed to save settings. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  const testMcpConnection = async (source: 'grafana' | 'jaeger' | 'opensearch') => {
    if (!config) return;
    const sourceConfig = config.mcpConnections[source];
    if (!sourceConfig.endpointUrl) {
      return;
    }

    setTestingMcpConnections(prev => ({ ...prev, [source]: true }));
    setMcpConnectionTestResults(prev => ({ ...prev, [source]: null }));

    try {
      const connectionData: TestConnectionRequest = {
        observability_system: source,
        enabled: sourceConfig.enabled,
        connection_config: {
          connection_type: "streamable-http",
          endpoint_url: sourceConfig.endpointUrl,
          http_headers: sourceConfig.httpHeaders
        }
      };

      const  responseData = await testConnectionMutation.mutateAsync(connectionData);
      setMcpConnectionTestResults(prev => ({ ...prev, [source]: responseData.data.success ? "success" :"error" }));
    } catch (error) {
      console.error(`${source} connection test failed:`, error);
      setMcpConnectionTestResults(prev => ({ ...prev, [source]: "error" }));
    } finally {
      setTestingMcpConnections(prev => ({ ...prev, [source]: false }));
    }
  };

  const testConfluenceConnection = async () => {
    if (!config || !config.externalRunbookConfig?.confluence) return;
    const confluenceConfig = config.externalRunbookConfig.confluence;

    if (!confluenceConfig.base_url || !confluenceConfig.username || !confluenceConfig.api_token) {
      return;
    }

    setTestingConfluence(true);
    setConfluenceTestResult(null);

    try {
      const response = await apiClient.post('/runbooks/validate-confluence', {
        base_url: confluenceConfig.base_url,
        username: confluenceConfig.username,
        api_token: confluenceConfig.api_token
      });

      const data = response.data;
      setConfluenceTestResult(data.status === 'success' ? 'success' : 'error');

      if (data.status === 'success') {
        toast.success(`Connected to Confluence as ${data.user}`);
      } else {
        toast.error(`Confluence connection failed: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Confluence connection test failed:', error);
      setConfluenceTestResult('error');
      toast.error('Confluence connection test failed');
    } finally {
      setTestingConfluence(false);
    }
  };

  const testDiagnosticConnection = async (index: number) => {
    if (!config || !config.diagnosticMcpServers[index]) return;
    const serverConfig = config.diagnosticMcpServers[index];
    if (!serverConfig.connectionConfig.endpointUrl) {
      return;
    }

    setTestingDiagnosticConnections(prev => ({ ...prev, [index]: true }));
    setDiagnosticConnectionTestResults(prev => ({ ...prev, [index]: null }));

    try {
      // Build connection config, excluding certificate fields if mTLS is disabled
      const connectionConfig: any = {
        connection_type: "streamable-http",
        endpoint_url: serverConfig.connectionConfig.endpointUrl,
        http_headers: serverConfig.connectionConfig.httpHeaders,
        mtls_enabled: serverConfig.connectionConfig.mtlsEnabled
      };

      // Only include certificate fields if mTLS is enabled
      if (serverConfig.connectionConfig.mtlsEnabled) {
        connectionConfig.ca_cert = serverConfig.connectionConfig.caCert;
        connectionConfig.client_cert = serverConfig.connectionConfig.clientCert;
        connectionConfig.client_key = serverConfig.connectionConfig.clientKey;
      }

      const connectionData: any = {
        enabled: serverConfig.enabled,
        connection_config: connectionConfig
      };

      const responseData = await testConnectionMutation.mutateAsync(connectionData);
      setDiagnosticConnectionTestResults(prev => ({ ...prev, [index]: responseData.data.success ? "success" : "error" }));
    } catch (error) {
      console.error(`Diagnostic server ${index} connection test failed:`, error);
      setDiagnosticConnectionTestResults(prev => ({ ...prev, [index]: "error" }));
    } finally {
      setTestingDiagnosticConnections(prev => ({ ...prev, [index]: false }));
    }
  };

  const testCodeTriageConnection = async () => {
    if (!config?.codeTriaging.baseUrl) {
      return;
    }

    setTestingCodeTriageAgent(true);
    setCodeTriageTestResult(null);

    try {
      // Send data in the format expected by the backend (CodeTriagingAgent model)
      const connectionData: any = {
        enabled: config.codeTriaging.enabled,
        base_url: config.codeTriaging.baseUrl,
        timeout_seconds: config.codeTriaging.timeoutSeconds,
        max_retries: config.codeTriaging.maxRetries
      };

      const responseData = await testConnectionMutation.mutateAsync(connectionData);
      setCodeTriageTestResult(responseData.data.success ? "success" : "error");
    } catch (error) {
      console.error("Code Triage Agent connection test failed:", error);
      setCodeTriageTestResult("error");
    } finally {
      setTestingCodeTriageAgent(false);
    }
  };

  const getValidationErrors = (): string[] => {
    if (!config) return ["Configuration not loaded"];

    const errors: string[] = [];

    // Check custom deployment validation - only when deployment is "custom"
    if (config.deployment === "custom") {
      if (!config.customDeployment) {
        errors.push("Custom deployment configuration is required");
        return errors;
      }

      const { llm, embedding } = config.customDeployment;

      // Check LLM configuration
      if (llm.provider === "azure-openai") {
        if (!llm.azureOpenAI) {
          errors.push("Azure OpenAI LLM configuration is required");
        } else {
          if (!llm.azureOpenAI.apiKey.trim()) {
            errors.push("LLM API Key is required");
          }
          if (!llm.azureOpenAI.endpointUrl.trim()) {
            errors.push("LLM Endpoint URL is required");
          }
          if (!llm.azureOpenAI.deploymentName.trim()) {
            errors.push("LLM Deployment Name is required");
          }
        }
      }
      if (llm.provider === "aws-bedrock-claude") {
        if (!llm.awsBedrock) {
          errors.push("AWS Bedrock LLM configuration is required");
        } else {
          if (!llm.awsBedrock.apiKey.trim()) {
            errors.push("AWS LLM API Key is required");
          }
          if (!llm.awsBedrock.region.trim()) {
            errors.push("AWS Region is required");
          }
          if (!llm.awsBedrock.modelId.trim()) {
            errors.push("AWS Model ID is required");
          }
        }
      }
      if (llm.provider === "azure-anthropic") {
        if (!llm.azureAnthropic) {
          errors.push("Azure Anthropic LLM configuration is required");
        } else {
          if (!llm.azureAnthropic.apiKey.trim()) {
            errors.push("Azure Anthropic API Key is required");
          }
          if (!llm.azureAnthropic.endpointUrl.trim()) {
            errors.push("Azure Anthropic Endpoint URL is required");
          }
          // Validate URL format
          try {
            new URL(llm.azureAnthropic.endpointUrl);
          } catch {
            errors.push("Azure Anthropic Endpoint URL must be a valid HTTPS URL");
          }
          if (!llm.azureAnthropic.modelId.trim()) {
            errors.push("Azure Anthropic Model ID is required");
          }
        }
      }

      // Check secondary LLM configuration - only when not same as primary
      if (!config.customDeployment.secondaryLlm.sameAsPrimary) {
        const { secondaryLlm } = config.customDeployment;

        if (!secondaryLlm.provider) {
          errors.push("Secondary LLM provider is required when not using same as primary");
        } else if (secondaryLlm.provider === "azure-openai") {
          if (!secondaryLlm.azureOpenAI) {
            errors.push("Secondary Azure OpenAI LLM configuration is required");
          } else {
            if (!secondaryLlm.azureOpenAI.apiKey.trim()) {
              errors.push("Secondary LLM API Key is required");
            }
            if (!secondaryLlm.azureOpenAI.endpointUrl.trim()) {
              errors.push("Secondary LLM Endpoint URL is required");
            }
            if (!secondaryLlm.azureOpenAI.deploymentName.trim()) {
              errors.push("Secondary LLM Deployment Name is required");
            }
          }
        } else if (secondaryLlm.provider === "aws-bedrock-claude") {
          if (!secondaryLlm.awsBedrock) {
            errors.push("Secondary AWS Bedrock LLM configuration is required");
          } else {
            if (!secondaryLlm.awsBedrock.apiKey.trim()) {
              errors.push("Secondary AWS LLM API Key is required");
            }
            if (!secondaryLlm.awsBedrock.region.trim()) {
              errors.push("Secondary AWS Region is required");
            }
            if (!secondaryLlm.awsBedrock.modelId.trim()) {
              errors.push("Secondary AWS Model ID is required");
            }
          }
        } else if (secondaryLlm.provider === "azure-anthropic") {
          if (!secondaryLlm.azureAnthropic) {
            errors.push("Secondary Azure Anthropic LLM configuration is required");
          } else {
            if (!secondaryLlm.azureAnthropic.apiKey.trim()) {
              errors.push("Secondary Azure Anthropic API Key is required");
            }
            if (!secondaryLlm.azureAnthropic.endpointUrl.trim()) {
              errors.push("Secondary Azure Anthropic Endpoint URL is required");
            }
            // Validate URL format
            try {
              new URL(secondaryLlm.azureAnthropic.endpointUrl);
            } catch {
              errors.push("Secondary Azure Anthropic Endpoint URL must be a valid HTTPS URL");
            }
            if (!secondaryLlm.azureAnthropic.modelId.trim()) {
              errors.push("Secondary Azure Anthropic Model ID is required");
            }
          }
        }
      }

      // Check embedding configuration (always Azure OpenAI for now)
      if (!embedding.azureOpenAI) {
        errors.push("Embedding configuration is required");
      } else {
        if (!embedding.azureOpenAI.apiKey.trim()) {
          errors.push("Embedding API Key is required");
        }
        if (!embedding.azureOpenAI.endpointUrl.trim()) {
          errors.push("Embedding Endpoint URL is required");
        }
        if (!embedding.azureOpenAI.deploymentName.trim()) {
          errors.push("Embedding Deployment Name is required");
        }
      }
    }

    // Check code triaging validation - only when enabled
    if (config.codeTriaging.enabled) {
      if (!config.codeTriaging.baseUrl.trim()) {
        errors.push("Code Triaging Service Base URL is required when enabled");
      }
      if (!config.codeTriaging.timeoutSeconds || config.codeTriaging.timeoutSeconds < 1 || config.codeTriaging.timeoutSeconds > 300) {
        errors.push("Code Triaging Timeout must be between 1 and 300 seconds");
      }
      if (config.codeTriaging.maxRetries < 0 || config.codeTriaging.maxRetries > 10) {
        errors.push("Code Triaging Max Retries must be between 0 and 10");
      }
    }

    // Check MCP connections validation - at least one must be enabled
    const grafanaValid = config.mcpConnections.grafana.enabled && config.mcpConnections.grafana.endpointUrl.trim();
    const jaegerValid = config.mcpConnections.jaeger.enabled && config.mcpConnections.jaeger.endpointUrl.trim();
    const opensearchValid = config.mcpConnections.opensearch.enabled && config.mcpConnections.opensearch.endpointUrl.trim();

    if (!grafanaValid && !jaegerValid && !opensearchValid) {
      errors.push("At least one MCP connection (Grafana, Jaeger, or OpenSearch) must be enabled with a valid endpoint URL");
    }

    // Individual MCP connection validation
    if (config.mcpConnections.grafana.enabled) {
      if (!config.mcpConnections.grafana.endpointUrl.trim()) {
        errors.push("Grafana MCP Endpoint URL is required when enabled");
      }
    }

    if (config.mcpConnections.jaeger.enabled) {
      if (!config.mcpConnections.jaeger.endpointUrl.trim()) {
        errors.push("Jaeger MCP Endpoint URL is required when enabled");
      }
    }

    if (config.mcpConnections.opensearch.enabled) {
      if (!config.mcpConnections.opensearch.endpointUrl.trim()) {
        errors.push("OpenSearch MCP Endpoint URL is required when enabled");
      }
    }

    return errors;
  };

  // Function to manually refresh validation errors
  const refreshValidationErrors = () => {
    if (showValidationErrors && config) {
      const currentErrors = getValidationErrors();
      setValidationErrors(currentErrors);
      if (currentErrors.length === 0) {
        setShowValidationErrors(false);
      }
    }
  };


  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-loading" />
          <span className="text-foreground">Loading configuration...</span>
        </div>
      </div>
    );
  }
else if (isError || !config) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex justify-center w-full">
            <Card className="border border-border p-6 box-shadow w-full">
              <div className="flex flex-col items-center justify-center py-16 px-4">
            <AlertCircle className="h-12 w-12 text-danger" />
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">Failed to load configuration</h3>
              <p className="text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'Failed to load configuration'}
              </p>
              <Button onClick={() =>refetch()} variant="outline">
                Try Again
              </Button>
            </div>
          </div>
            </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header with unsaved changes indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="page-title font-bold title-lg-header">Setup</h1>
          {hasUnsavedChanges && (
            <Badge variant="secondary" className="bg-warning-light text-warning-dark border-warning">
              Unsaved changes
            </Badge>
          )}
          {/* isError check removed - if isError was true, we would have returned early above (line 518) */}
        </div>
      </div>

      {/* Validation Errors Display */}
      {showValidationErrors && <ValidationErrors errors={validationErrors} />}

      {/* Tab-based Configuration */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="w-full">
          <TabsTrigger value="general">General Settings</TabsTrigger>
          <TabsTrigger value="agent">Agent Configuration</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
          <TabsTrigger value="advanced">Advanced Settings</TabsTrigger>
        </TabsList>

        {/* General Settings Tab */}
        <TabsContent value="general" className="mt-6">
          <div className="space-y-8">
            {/* Automatic Triage Toggle */}
            <AutomaticTriageToggle
              enabled={config.automaticTriage}
              onToggle={(enabled) => setConfig((prev: any) => ({ ...prev, automaticTriage: enabled }))}
            />

            {/* Alert Grouping Toggle */}
            <AlertGroupingToggle
              enabled={config.alertGroupingEnabled}
              onToggle={(enabled) => setConfig((prev: any) => ({ ...prev, alertGroupingEnabled: enabled }))}
            />

            {/* Alert Triage Levels */}
            <AlertTriageLevels
              triageLevels={config.triageLevels}
              onUpdate={updateTriageLevels}
            />
          </div>
        </TabsContent>

        {/* Agent Configuration Tab */}
        <TabsContent value="agent" className="mt-6">
          <div className="space-y-8">
            {/* Agent Deployment */}
            <AgentDeployment
              deployment={config.deployment}
              customDeployment={config.customDeployment ?? {
                llm: {
                  provider: "azure-openai",
                  azureOpenAI: {
                    apiKey: "",
                    endpointUrl: "",
                    deploymentName: "",
                    apiVersion: "",
                    priceUsdPer1kIpTokens: 0,
                    priceUsdPer1kOpTokens: 0
                  }
                },
                secondaryLlm: {
                  sameAsPrimary: true
                },
                embedding: {
                  provider: "azure-openai",
                  azureOpenAI: {
                    apiKey: "",
                    endpointUrl: "",
                    deploymentName: "",
                    apiVersion: ""
                  }
                }
              }}
              onDeploymentChange={(value) => setConfig((prev: any) => ({ ...prev, deployment: value }))}
              onConfigUpdate={(customDeployment) => setConfig((prev: any) => ({ ...prev, customDeployment }))}
              refreshValidationErrors={refreshValidationErrors}
            />

            {/* Code Triaging Agent */}
            <CodeTriagingAgent
              codeTriaging={config.codeTriaging}
              onUpdate={(codeTriaging) => setConfig((prev: any) => ({ ...prev, codeTriaging }))}
              onTestConnection={testCodeTriageConnection}
              isTesting={testingCodeTriageAgent}
              testResult={codeTriageTestResult}
              refreshValidationErrors={refreshValidationErrors}
            />

            {/* Orchestrator Configuration */}
            {/* <OrchestratorConfiguration
              orchestratorAgents={config.orchestratorAgents}
              onUpdate={(agents) => setConfig((prev: any) => ({ ...prev, orchestratorAgents: agents }))}
            /> */}
          </div>
        </TabsContent>

        {/* Integrations Tab */}
        <TabsContent value="integrations" className="mt-6">
          <div className="space-y-8">
            {/* MCP Connections */}
            <MCPConnections
              mcpConnections={config.mcpConnections}
              onUpdate={(mcpConnections) => setConfig((prev: any) => ({ ...prev, mcpConnections }))}
              onTestConnection={testMcpConnection}
              testingMcpConnections={testingMcpConnections}
              mcpConnectionTestResults={mcpConnectionTestResults}
              diagnosticMcpServers={config.diagnosticMcpServers}
              onUpdateDiagnosticServers={(servers) => setConfig((prev: any) => ({ ...prev, diagnosticMcpServers: servers }))}
              onTestDiagnosticConnection={testDiagnosticConnection}
              testingDiagnosticConnections={testingDiagnosticConnections}
              diagnosticConnectionTestResults={diagnosticConnectionTestResults}
              refreshValidationErrors={refreshValidationErrors}
            />

            {/* External Runbook Sources */}
            <ExternalRunbookSources
              externalRunbookConfig={config.externalRunbookConfig}
              onUpdate={(externalRunbookConfig) => setConfig((prev: any) => ({ ...prev, externalRunbookConfig }))}
              onTestConfluence={testConfluenceConnection}
              testingConfluence={testingConfluence}
              confluenceTestResult={confluenceTestResult}
              refreshValidationErrors={refreshValidationErrors}
            />
          </div>
        </TabsContent>

        {/* Advanced Settings Tab */}
        <TabsContent value="advanced" className="mt-6">
          <div className="space-y-8">
            {/* Chaos System Toggle */}
            <ChaosSystemToggle
              enabled={config.chaosSystemEnabled}
              onToggle={(enabled) => setConfig((prev: any) => ({ ...prev, chaosSystemEnabled: enabled }))}
            />
          </div>
        </TabsContent>
      </Tabs>

      {/* Bottom action bar */}
      <div className="flex items-center justify-end pt-6 border-border">
        <Button
          onClick={handleSave}
          disabled={isSaving || !hasUnsavedChanges}
          className={cn(
            "min-w-[100px] active-range-bg",
            showValidationErrors && validationErrors.length > 0 && "border-red-300 hover:border-red-400"
          )}
        >
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              {showValidationErrors && validationErrors.length > 0 && (
                <AlertTriangle className="h-4 w-4 mr-2 text-warning" />
              )}
              Save Settings
            </>
          )}
        </Button>
      </div>
    </div>
  );
}