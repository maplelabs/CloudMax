export interface HttpHeader {
  key: string;
  value: string;
}

export interface DiagnosticMcpServer {
  name: string;
  enabled: boolean;
  connectionConfig: {
    connectionType: "streamable-http";
    endpointUrl: string;
    httpHeaders: HttpHeader[];
    mtlsEnabled: boolean;
    caCert: string;
    clientCert: string;
    clientKey: string;
  };
}

export interface LlmConfig {
  llm_type: "azure-openai" | "aws-bedrock-claude" | "azure-anthropic";
  api_key: string;
  endpoint_url?: string;
  deployment_name?: string;
  api_version?: string;
  region?: string;
  model_id?: string;
  price_usd_per_1k_ip_tokens?: number;
  price_usd_per_1k_op_tokens?: number;
}

export interface EmbeddingConfig {
  embedding_type: "azure-openai";
  api_key: string;
  endpoint_url: string;
  deployment_name: string;
  api_version: string;
}

export interface SecondaryLlmConfig {
  same_as_primary: boolean;
  llm_config: Partial<LlmConfig>;
}

export interface CustomDeploymentConfig {
  primary_llm_config: LlmConfig;
  secondary_llm_config: SecondaryLlmConfig;
  embedding_config: EmbeddingConfig;
}

export interface ConnectionConfig {
  connection_type: "streamable-http";
  endpoint_url: string;
  http_headers: HttpHeader[];
}

export interface SystemConfig {
  observability_system: "grafana" | "jaeger" | "opensearch";
  enabled: boolean;
  connection_config: ConnectionConfig;
}

export interface McpConnectionsConfig {
  systems: SystemConfig[];
}

export interface AlertTriageConfig {
  enabled_severities: string[];
}

export interface CodeTriagingAgentConfig {
  enabled: boolean;
  base_url: string;
  timeout_seconds: number;
  max_retries: number;
}

export interface DiagnosticMcpServerApi {
  name: string;
  enabled: boolean;
  connection_config: {
    connection_type: "streamable-http";
    endpoint_url: string;
    http_headers: HttpHeader[];
    mtls_enabled: boolean;
    ca_cert: string;
    client_cert: string;
    client_key: string;
  };
}

export interface ApiConfigResponse {
  alert_triage_config: AlertTriageConfig;
  deployment: "custom" | "azure";
  custom_deployment: CustomDeploymentConfig;
  mcp_connections: McpConnectionsConfig;
  diagnostic_mcp_servers?: {
    servers: DiagnosticMcpServerApi[];
  };
  external_runbook_config?: {
    confluence?: {
      enabled: boolean;
      base_url: string;
      username: string;
      api_token: string;
    };
  };
  code_triaging_agent: CodeTriagingAgentConfig;
  orchestrator_agents: number;
  chaos_system_enabled: boolean;
  automatic_triage: boolean;
  default_config?: boolean;
}

export interface TestConnectionRequest {
  observability_system?: "grafana" | "jaeger" | "opensearch";
  enabled?: boolean;
  connection_config: {
    connection_type?: "streamable-http";
    endpoint_url?: string;
    http_headers?: HttpHeader[];
  };
}

export interface TestConnectionResponse {
  success: boolean;
  message?: string;
  error?: string;
}

export interface SetupConfig {
  triageLevels: {
    p1: boolean;
    p2: boolean;
    p3: boolean;
  };
  deployment: "custom" | "azure";
  customDeployment?: {
    llm: {
      provider: "azure-openai" | "aws-bedrock-claude" | "azure-anthropic";
      azureOpenAI?: {
        apiKey: string;
        endpointUrl: string;
        deploymentName: string;
        apiVersion: string;
        priceUsdPer1kIpTokens?: number;
        priceUsdPer1kOpTokens?: number;
      };
      awsBedrock?: {
        apiKey: string;
        region: string;
        modelId: string;
        priceUsdPer1kIpTokens?: number;
        priceUsdPer1kOpTokens?: number;
      };
      azureAnthropic?: {
        apiKey: string;
        endpointUrl: string;
        modelId: string;
        priceUsdPer1kIpTokens?: number;
        priceUsdPer1kOpTokens?: number;
      };
    };
    secondaryLlm: {
      sameAsPrimary: boolean;
      provider?: "azure-openai" | "aws-bedrock-claude" | "azure-anthropic";
      azureOpenAI?: {
        apiKey: string;
        endpointUrl: string;
        deploymentName: string;
        apiVersion: string;
        priceUsdPer1kIpTokens?: number;
        priceUsdPer1kOpTokens?: number;
      };
      awsBedrock?: {
        apiKey: string;
        region: string;
        modelId: string;
        priceUsdPer1kIpTokens?: number;
        priceUsdPer1kOpTokens?: number;
      };
      azureAnthropic?: {
        apiKey: string;
        endpointUrl: string;
        modelId: string;
        priceUsdPer1kIpTokens?: number;
        priceUsdPer1kOpTokens?: number;
      };
    };
    embedding: {
      provider: "azure-openai";
      azureOpenAI: {
        apiKey: string;
        endpointUrl: string;
        deploymentName: string;
        apiVersion: string;
      };
    };
  };
  mcpConnections: {
    grafana: {
      enabled: boolean;
      endpointUrl: string;
      httpHeaders: HttpHeader[];
    };
    jaeger: {
      enabled: boolean;
      endpointUrl: string;
      httpHeaders: HttpHeader[];
    };
    opensearch: {
      enabled: boolean;
      endpointUrl: string;
      httpHeaders: HttpHeader[];
    };
  };
  externalRunbookConfig?: {
    confluence?: {
      enabled: boolean;
      base_url: string;
      username: string;
      api_token: string;
    };
    // Future: notion, github_wiki, etc.
  };
  diagnosticMcpServers: DiagnosticMcpServer[];
  codeTriaging: {
    enabled: boolean;
    baseUrl: string;
    timeoutSeconds: number;
    maxRetries: number;
  };
  orchestratorAgents: number;
  chaosSystemEnabled: boolean;
  automaticTriage: boolean;
  alertGroupingEnabled: boolean;
}

// Simple hash function for config comparison
export const generateConfigHash = (config: SetupConfig): string => {
  const normalizeConfig = (config: SetupConfig) => {
    return {
      ...config,
      // Normalize strings by trimming whitespace
      customDeployment: config.customDeployment ? {
        ...config.customDeployment,
        llm: {
          provider: config.customDeployment.llm.provider,
          // Only include the configuration for the active provider to avoid false changes
          ...(config.customDeployment.llm.provider === "azure-openai" && config.customDeployment.llm.azureOpenAI ? {
            azureOpenAI: {
              ...config.customDeployment.llm.azureOpenAI,
              apiKey: config.customDeployment.llm.azureOpenAI.apiKey.trim(),
              endpointUrl: config.customDeployment.llm.azureOpenAI.endpointUrl.trim(),
              deploymentName: config.customDeployment.llm.azureOpenAI.deploymentName.trim(),
            }
          } : {}),
          ...(config.customDeployment.llm.provider === "aws-bedrock-claude" && config.customDeployment.llm.awsBedrock ? {
            awsBedrock: {
              ...config.customDeployment.llm.awsBedrock,
              apiKey: config.customDeployment.llm.awsBedrock.apiKey.trim(),
              region: config.customDeployment.llm.awsBedrock.region.trim(),
              modelId: config.customDeployment.llm.awsBedrock.modelId.trim(),
            }
          } : {}),
          ...(config.customDeployment.llm.provider === "azure-anthropic" && config.customDeployment.llm.azureAnthropic ? {
            azureAnthropic: {
              ...config.customDeployment.llm.azureAnthropic,
              apiKey: config.customDeployment.llm.azureAnthropic.apiKey.trim(),
              endpointUrl: config.customDeployment.llm.azureAnthropic.endpointUrl.trim(),
              modelId: config.customDeployment.llm.azureAnthropic.modelId.trim(),
            }
          } : {}),
        },
        secondaryLlm: {
          sameAsPrimary: config.customDeployment.secondaryLlm.sameAsPrimary,
          provider: config.customDeployment.secondaryLlm.provider,
          ...(config.customDeployment.secondaryLlm.provider === "azure-openai" && config.customDeployment.secondaryLlm.azureOpenAI ? {
            azureOpenAI: {
              ...config.customDeployment.secondaryLlm.azureOpenAI,
              apiKey: config.customDeployment.secondaryLlm.azureOpenAI.apiKey.trim(),
              endpointUrl: config.customDeployment.secondaryLlm.azureOpenAI.endpointUrl.trim(),
              deploymentName: config.customDeployment.secondaryLlm.azureOpenAI.deploymentName.trim(),
            }
          } : {}),
          ...(config.customDeployment.secondaryLlm.provider === "aws-bedrock-claude" && config.customDeployment.secondaryLlm.awsBedrock ? {
            awsBedrock: {
              ...config.customDeployment.secondaryLlm.awsBedrock,
              apiKey: config.customDeployment.secondaryLlm.awsBedrock.apiKey.trim(),
              region: config.customDeployment.secondaryLlm.awsBedrock.region.trim(),
              modelId: config.customDeployment.secondaryLlm.awsBedrock.modelId.trim(),
            }
          } : {}),
          ...(config.customDeployment.secondaryLlm.provider === "azure-anthropic" && config.customDeployment.secondaryLlm.azureAnthropic ? {
            azureAnthropic: {
              ...config.customDeployment.secondaryLlm.azureAnthropic,
              apiKey: config.customDeployment.secondaryLlm.azureAnthropic.apiKey.trim(),
              endpointUrl: config.customDeployment.secondaryLlm.azureAnthropic.endpointUrl.trim(),
              modelId: config.customDeployment.secondaryLlm.azureAnthropic.modelId.trim(),
            }
          } : {}),
        },
        embedding: {
          ...config.customDeployment.embedding,
          azureOpenAI: {
            ...config.customDeployment.embedding.azureOpenAI,
            apiKey: config.customDeployment.embedding.azureOpenAI.apiKey.trim(),
            endpointUrl: config.customDeployment.embedding.azureOpenAI.endpointUrl.trim(),
            deploymentName: config.customDeployment.embedding.azureOpenAI.deploymentName.trim(),
          }
        }
      } : undefined,
      mcpConnections: {
        grafana: {
          ...config.mcpConnections.grafana,
          endpointUrl: config.mcpConnections.grafana.endpointUrl.trim(),
        },
        jaeger: {
          ...config.mcpConnections.jaeger,
          endpointUrl: config.mcpConnections.jaeger.endpointUrl.trim(),
        },
        opensearch: {
          ...config.mcpConnections.opensearch,
          endpointUrl: config.mcpConnections.opensearch.endpointUrl.trim(),
        }
      },
      diagnosticMcpServers: config.diagnosticMcpServers.map(server => ({
        ...server,
        name: server.name.trim(),
        connectionConfig: {
          ...server.connectionConfig,
          endpointUrl: server.connectionConfig.endpointUrl.trim()
        }
      })),
      codeTriaging: {
        ...config.codeTriaging,
        baseUrl: config.codeTriaging.baseUrl.trim(),
        apiKey: config.codeTriaging.apiKey.trim(),
        notes: config.codeTriaging.notes.trim(),
      }
    };
  };

  try {
    const normalized = normalizeConfig(config);
    const str = JSON.stringify(normalized);

    // Simple hash function (djb2)
    let hash = 5381;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash) + str.charCodeAt(i);
    }
    return hash.toString(36);
  } catch (error) {
    // Fallback to timestamp if hashing fails
    return Date.now().toString();
  }
};

export const mapApiToComponentConfig = (apiConfig: ApiConfigResponse): SetupConfig => {
  const grafanaSystem = apiConfig.mcp_connections.systems.find(s => s.observability_system === "grafana");
  const jaegerSystem = apiConfig.mcp_connections.systems.find(s => s.observability_system === "jaeger");
  const opensearchSystem = apiConfig.mcp_connections.systems.find(s => s.observability_system === "opensearch");

  const secondaryLlmConfig = apiConfig.custom_deployment?.secondary_llm_config;
  const sameAsPrimary = secondaryLlmConfig?.same_as_primary ?? true;
  const secondaryLlm = secondaryLlmConfig?.llm_config;

  return {
    triageLevels: {
      p1: apiConfig.alert_triage_config.enabled_severities.includes("P1"),
      p2: apiConfig.alert_triage_config.enabled_severities.includes("P2"),
      p3: apiConfig.alert_triage_config.enabled_severities.includes("P3")
    },
    deployment: apiConfig.deployment,
    chaosSystemEnabled: apiConfig.chaos_system_enabled ?? false,
    customDeployment: apiConfig.custom_deployment ? {
      llm: {
        provider: apiConfig.custom_deployment.primary_llm_config.llm_type,
        azureOpenAI: apiConfig.custom_deployment.primary_llm_config.llm_type === "azure-openai" ? {
          apiKey: apiConfig.custom_deployment.primary_llm_config.api_key,
          endpointUrl: apiConfig.custom_deployment.primary_llm_config.endpoint_url,
          deploymentName: apiConfig.custom_deployment.primary_llm_config.deployment_name,
          apiVersion: apiConfig.custom_deployment.primary_llm_config.api_version,
          priceUsdPer1kIpTokens: apiConfig.custom_deployment.primary_llm_config.price_usd_per_1k_ip_tokens,
          priceUsdPer1kOpTokens: apiConfig.custom_deployment.primary_llm_config.price_usd_per_1k_op_tokens
        } : undefined,
        awsBedrock: apiConfig.custom_deployment.primary_llm_config.llm_type === "aws-bedrock-claude" ? {
          apiKey: apiConfig.custom_deployment.primary_llm_config.api_key,
          region: apiConfig.custom_deployment.primary_llm_config.region || "",
          modelId: apiConfig.custom_deployment.primary_llm_config.model_id || apiConfig.custom_deployment.primary_llm_config.deployment_name,
          priceUsdPer1kIpTokens: apiConfig.custom_deployment.primary_llm_config.price_usd_per_1k_ip_tokens,
          priceUsdPer1kOpTokens: apiConfig.custom_deployment.primary_llm_config.price_usd_per_1k_op_tokens
        } : undefined,
        azureAnthropic: apiConfig.custom_deployment.primary_llm_config.llm_type === "azure-anthropic" ? {
          apiKey: apiConfig.custom_deployment.primary_llm_config.api_key,
          endpointUrl: apiConfig.custom_deployment.primary_llm_config.endpoint_url || "",
          modelId: apiConfig.custom_deployment.primary_llm_config.model_id || "claude-haiku-4-5",
          priceUsdPer1kIpTokens: apiConfig.custom_deployment.primary_llm_config.price_usd_per_1k_ip_tokens,
          priceUsdPer1kOpTokens: apiConfig.custom_deployment.primary_llm_config.price_usd_per_1k_op_tokens
        } : undefined
      },
      secondaryLlm: {
        sameAsPrimary,
        provider: !sameAsPrimary && secondaryLlm?.llm_type ? secondaryLlm.llm_type : undefined,
        azureOpenAI: !sameAsPrimary && secondaryLlm?.llm_type === "azure-openai" ? {
          apiKey: secondaryLlm.api_key || "",
          endpointUrl: secondaryLlm.endpoint_url || "",
          deploymentName: secondaryLlm.deployment_name || "",
          apiVersion: secondaryLlm.api_version || "2023-12-01-preview",
          priceUsdPer1kIpTokens: secondaryLlm.price_usd_per_1k_ip_tokens,
          priceUsdPer1kOpTokens: secondaryLlm.price_usd_per_1k_op_tokens
        } : undefined,
        awsBedrock: !sameAsPrimary && secondaryLlm?.llm_type === "aws-bedrock-claude" ? {
          apiKey: secondaryLlm.api_key || "",
          region: secondaryLlm.region || "",
          modelId: secondaryLlm.model_id || secondaryLlm.deployment_name || "",
          priceUsdPer1kIpTokens: secondaryLlm.price_usd_per_1k_ip_tokens,
          priceUsdPer1kOpTokens: secondaryLlm.price_usd_per_1k_op_tokens
        } : undefined,
        azureAnthropic: !sameAsPrimary && secondaryLlm?.llm_type === "azure-anthropic" ? {
          apiKey: secondaryLlm.api_key || "",
          endpointUrl: secondaryLlm.endpoint_url || "",
          modelId: secondaryLlm.model_id || "claude-haiku-4-5",
          priceUsdPer1kIpTokens: secondaryLlm.price_usd_per_1k_ip_tokens,
          priceUsdPer1kOpTokens: secondaryLlm.price_usd_per_1k_op_tokens
        } : undefined
      },
      embedding: {
        provider: "azure-openai",
        azureOpenAI: {
          apiKey: apiConfig.custom_deployment.embedding_config.api_key,
          endpointUrl: apiConfig.custom_deployment.embedding_config.endpoint_url,
          deploymentName: apiConfig.custom_deployment.embedding_config.deployment_name,
          apiVersion: apiConfig.custom_deployment.embedding_config.api_version
        }
      }
    } : undefined,
    mcpConnections: {
      grafana: {
        enabled: grafanaSystem?.enabled || false,
        endpointUrl: grafanaSystem?.connection_config.endpoint_url || "",
        httpHeaders: grafanaSystem?.connection_config.http_headers || []
      },
      jaeger: {
        enabled: jaegerSystem?.enabled || false,
        endpointUrl: jaegerSystem?.connection_config.endpoint_url || "",
        httpHeaders: jaegerSystem?.connection_config.http_headers || []
      },
      opensearch: {
        enabled: opensearchSystem?.enabled || false,
        endpointUrl: opensearchSystem?.connection_config.endpoint_url || "",
        httpHeaders: opensearchSystem?.connection_config.http_headers || []
      }
    },
    diagnosticMcpServers: apiConfig.diagnostic_mcp_servers?.servers.map(server => ({
      name: server.name,
      enabled: server.enabled,
      connectionConfig: {
        connectionType: "streamable-http" as const,
        endpointUrl: server.connection_config.endpoint_url,
        httpHeaders: server.connection_config.http_headers,
        mtlsEnabled: server.connection_config.mtls_enabled,
        caCert: server.connection_config.ca_cert,
        clientCert: server.connection_config.client_cert,
        clientKey: server.connection_config.client_key
      }
    })) || [],
    externalRunbookConfig: apiConfig.external_runbook_config ? {
      confluence: apiConfig.external_runbook_config.confluence ? {
        enabled: apiConfig.external_runbook_config.confluence.enabled,
        base_url: apiConfig.external_runbook_config.confluence.base_url,
        username: apiConfig.external_runbook_config.confluence.username,
        api_token: apiConfig.external_runbook_config.confluence.api_token
      } : undefined
    } : undefined,
    codeTriaging: {
      enabled: apiConfig.code_triaging_agent.enabled,
      baseUrl: apiConfig.code_triaging_agent.base_url || '',
      apiKey: apiConfig.code_triaging_agent.api_key || '',
      timeoutSeconds: apiConfig.code_triaging_agent.timeout_seconds || 30,
      maxRetries: apiConfig.code_triaging_agent.max_retries ?? 3,
      notes: apiConfig.code_triaging_agent.notes || ''
    },
    orchestratorAgents: apiConfig.orchestrator_agents,
    automaticTriage: apiConfig.automatic_triage ?? false,
    alertGroupingEnabled: apiConfig.alert_grouping_enabled ?? true
  };
};

export const mapComponentToApiConfig = (componentConfig: SetupConfig): ApiConfigResponse => {
  // Build enabled severities array
  const enabledSeverities: string[] = [];
  if (componentConfig.triageLevels.p1) enabledSeverities.push("P1");
  if (componentConfig.triageLevels.p2) enabledSeverities.push("P2");
  if (componentConfig.triageLevels.p3) enabledSeverities.push("P3");

  // Build systems array - only include enabled systems with valid URLs
  const systems = [];

  if (componentConfig.mcpConnections.grafana.enabled && componentConfig.mcpConnections.grafana.endpointUrl.trim()) {
    systems.push({
      observability_system: "grafana" as const,
      enabled: componentConfig.mcpConnections.grafana.enabled,
      connection_config: {
        connection_type: "streamable-http" as const,
        endpoint_url: componentConfig.mcpConnections.grafana.endpointUrl,
        http_headers: componentConfig.mcpConnections.grafana.httpHeaders
      }
    });
  }

  if (componentConfig.mcpConnections.jaeger.enabled && componentConfig.mcpConnections.jaeger.endpointUrl.trim()) {
    systems.push({
      observability_system: "jaeger" as const,
      enabled: componentConfig.mcpConnections.jaeger.enabled,
      connection_config: {
        connection_type: "streamable-http" as const,
        endpoint_url: componentConfig.mcpConnections.jaeger.endpointUrl,
        http_headers: componentConfig.mcpConnections.jaeger.httpHeaders
      }
    });
  }

  if (componentConfig.mcpConnections.opensearch.enabled && componentConfig.mcpConnections.opensearch.endpointUrl.trim()) {
    systems.push({
      observability_system: "opensearch" as const,
      enabled: componentConfig.mcpConnections.opensearch.enabled,
      connection_config: {
        connection_type: "streamable-http" as const,
        endpoint_url: componentConfig.mcpConnections.opensearch.endpointUrl,
        http_headers: componentConfig.mcpConnections.opensearch.httpHeaders
      }
    });
  }

  // Build primary LLM config based on provider
  const primaryLlmConfig = componentConfig.deployment === "custom" && componentConfig.customDeployment?.llm.provider === "aws-bedrock-claude" ? {
    llm_type: "aws-bedrock-claude" as const,
    api_key: componentConfig.customDeployment?.llm.awsBedrock?.apiKey || "",
    region: componentConfig.customDeployment?.llm.awsBedrock?.region || "",
    model_id: componentConfig.customDeployment?.llm.awsBedrock?.modelId || "",
    price_usd_per_1k_ip_tokens: componentConfig.customDeployment?.llm.awsBedrock?.priceUsdPer1kIpTokens,
    price_usd_per_1k_op_tokens: componentConfig.customDeployment?.llm.awsBedrock?.priceUsdPer1kOpTokens
  } : componentConfig.deployment === "custom" && componentConfig.customDeployment?.llm.provider === "azure-anthropic" ? {
    llm_type: "azure-anthropic" as const,
    api_key: componentConfig.customDeployment?.llm.azureAnthropic?.apiKey || "",
    endpoint_url: componentConfig.customDeployment?.llm.azureAnthropic?.endpointUrl || "",
    model_id: componentConfig.customDeployment?.llm.azureAnthropic?.modelId || "claude-haiku-4-5",
    price_usd_per_1k_ip_tokens: componentConfig.customDeployment?.llm.azureAnthropic?.priceUsdPer1kIpTokens,
    price_usd_per_1k_op_tokens: componentConfig.customDeployment?.llm.azureAnthropic?.priceUsdPer1kOpTokens
  } : {
    llm_type: "azure-openai" as const,
    api_key: componentConfig.deployment === "custom"
      ? (componentConfig.customDeployment?.llm.azureOpenAI?.apiKey || "")
      : "placeholder-key",
    endpoint_url: componentConfig.deployment === "custom"
      ? (componentConfig.customDeployment?.llm.azureOpenAI?.endpointUrl || "")
      : "https://placeholder.openai.azure.com/",
    deployment_name: componentConfig.deployment === "custom"
      ? (componentConfig.customDeployment?.llm.azureOpenAI?.deploymentName || "")
      : "placeholder-deployment",
    api_version: componentConfig.deployment === "custom"
      ? (componentConfig.customDeployment?.llm.azureOpenAI?.apiVersion || "2023-12-01-preview")
      : "2023-12-01-preview",
    price_usd_per_1k_ip_tokens: componentConfig.deployment === "custom"
      ? componentConfig.customDeployment?.llm.azureOpenAI?.priceUsdPer1kIpTokens
      : undefined,
    price_usd_per_1k_op_tokens: componentConfig.deployment === "custom"
      ? componentConfig.customDeployment?.llm.azureOpenAI?.priceUsdPer1kOpTokens
      : undefined
  };

  // Build secondary LLM config based on sameAsPrimary flag
  const secondaryLlmConfig: any = componentConfig.customDeployment?.secondaryLlm.sameAsPrimary
    ? {
        same_as_primary: true
      }
    : {
        same_as_primary: false,
        llm_config: componentConfig.customDeployment?.secondaryLlm.provider === "aws-bedrock-claude"
          ? {
              llm_type: "aws-bedrock-claude" as const,
              api_key: componentConfig.customDeployment?.secondaryLlm.awsBedrock?.apiKey || "",
              region: componentConfig.customDeployment?.secondaryLlm.awsBedrock?.region || "",
              model_id: componentConfig.customDeployment?.secondaryLlm.awsBedrock?.modelId || "",
              price_usd_per_1k_ip_tokens: componentConfig.customDeployment?.secondaryLlm.awsBedrock?.priceUsdPer1kIpTokens,
              price_usd_per_1k_op_tokens: componentConfig.customDeployment?.secondaryLlm.awsBedrock?.priceUsdPer1kOpTokens
            }
          : componentConfig.customDeployment?.secondaryLlm.provider === "azure-anthropic"
          ? {
              llm_type: "azure-anthropic" as const,
              api_key: componentConfig.customDeployment?.secondaryLlm.azureAnthropic?.apiKey || "",
              endpoint_url: componentConfig.customDeployment?.secondaryLlm.azureAnthropic?.endpointUrl || "",
              model_id: componentConfig.customDeployment?.secondaryLlm.azureAnthropic?.modelId || "claude-haiku-4-5",
              price_usd_per_1k_ip_tokens: componentConfig.customDeployment?.secondaryLlm.azureAnthropic?.priceUsdPer1kIpTokens,
              price_usd_per_1k_op_tokens: componentConfig.customDeployment?.secondaryLlm.azureAnthropic?.priceUsdPer1kOpTokens
            }
          : {
              llm_type: "azure-openai" as const,
              api_key: componentConfig.customDeployment?.secondaryLlm.azureOpenAI?.apiKey || "",
              endpoint_url: componentConfig.customDeployment?.secondaryLlm.azureOpenAI?.endpointUrl || "",
              deployment_name: componentConfig.customDeployment?.secondaryLlm.azureOpenAI?.deploymentName || "",
              api_version: componentConfig.customDeployment?.secondaryLlm.azureOpenAI?.apiVersion || "2023-12-01-preview",
              price_usd_per_1k_ip_tokens: componentConfig.customDeployment?.secondaryLlm.azureOpenAI?.priceUsdPer1kIpTokens,
              price_usd_per_1k_op_tokens: componentConfig.customDeployment?.secondaryLlm.azureOpenAI?.priceUsdPer1kOpTokens
            }
      };

  return {
    alert_triage_config: {
      enabled_severities: enabledSeverities
    },
    deployment: componentConfig.deployment,
    chaos_system_enabled: componentConfig.chaosSystemEnabled,
    custom_deployment: componentConfig.deployment === "custom" && componentConfig.customDeployment ? {
      primary_llm_config: primaryLlmConfig,
      secondary_llm_config: secondaryLlmConfig,
      embedding_config: {
        embedding_type: "azure-openai",
        api_key: componentConfig.customDeployment?.embedding.azureOpenAI?.apiKey || "",
        endpoint_url: componentConfig.customDeployment?.embedding.azureOpenAI?.endpointUrl || "",
        deployment_name: componentConfig.customDeployment?.embedding.azureOpenAI?.deploymentName || "",
        api_version: componentConfig.customDeployment?.embedding.azureOpenAI?.apiVersion || "2023-12-01-preview"
      }
    } : null,
    mcp_connections: {
      systems
    },
    diagnostic_mcp_servers: {
      servers: componentConfig.diagnosticMcpServers.map(server => ({
        name: server.name,
        enabled: server.enabled,
        connection_config: {
          connection_type: "streamable-http" as const,
          endpoint_url: server.connectionConfig.endpointUrl,
          http_headers: server.connectionConfig.httpHeaders,
          mtls_enabled: server.connectionConfig.mtlsEnabled,
          ca_cert: server.connectionConfig.caCert,
          client_cert: server.connectionConfig.clientCert,
          client_key: server.connectionConfig.clientKey
        }
      }))
    },
    external_runbook_config: componentConfig.externalRunbookConfig ? {
      confluence: componentConfig.externalRunbookConfig.confluence ? {
        enabled: componentConfig.externalRunbookConfig.confluence.enabled,
        base_url: componentConfig.externalRunbookConfig.confluence.base_url,
        username: componentConfig.externalRunbookConfig.confluence.username,
        api_token: componentConfig.externalRunbookConfig.confluence.api_token
      } : undefined
    } : undefined,
    code_triaging_agent: {
      enabled: componentConfig.codeTriaging.enabled,
      base_url: componentConfig.codeTriaging.baseUrl,
      api_key: componentConfig.codeTriaging.apiKey,
      notes: componentConfig.codeTriaging.notes,
      timeout_seconds: componentConfig.codeTriaging.timeoutSeconds || 30,
      max_retries: componentConfig.codeTriaging.maxRetries ?? 3
    },
    orchestrator_agents: componentConfig.orchestratorAgents,
    automatic_triage: componentConfig.automaticTriage,
    alert_grouping_enabled: componentConfig.alertGroupingEnabled,
    default_config: false
  };
};