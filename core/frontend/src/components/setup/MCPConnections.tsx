import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./../ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./../ui/tooltip";
import { Button } from "./../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./../ui/dialog";
import { HelpCircle, Plus } from "lucide-react";
import { MCPConnectionItemModal } from "./MCPConnectionItemModal";
import { DiagnosticMCPModal } from "./DiagnosticMCPModal";
import { DiagnosticMCPItem } from "./DiagnosticMCPItem";
import { SetupConfig, DiagnosticMcpServer } from "./../../types/config";
import apiClient from "../../service/api";

interface MCPConnectionsProps {
  mcpConnections: SetupConfig["mcpConnections"];
  onUpdate: (mcpConnections: SetupConfig["mcpConnections"]) => void;
  onTestConnection: (source: "grafana" | "jaeger" | "opensearch") => void;
  testingMcpConnections: { grafana: boolean; jaeger: boolean; opensearch: boolean };
  mcpConnectionTestResults: {
    grafana: "success" | "error" | null;
    jaeger: "success" | "error" | null;
    opensearch: "success" | "error" | null;
  };
  diagnosticMcpServers: DiagnosticMcpServer[];
  onUpdateDiagnosticServers: (servers: DiagnosticMcpServer[]) => void;
  onTestDiagnosticConnection?: (index: number) => void;
  testingDiagnosticConnections?: { [key: number]: boolean };
  diagnosticConnectionTestResults?: { [key: number]: "success" | "error" | null };
  refreshValidationErrors: () => void;
}

export function MCPConnections({
  mcpConnections,
  onUpdate,
  onTestConnection,
  testingMcpConnections,
  mcpConnectionTestResults,
  diagnosticMcpServers,
  onUpdateDiagnosticServers,
  onTestDiagnosticConnection,
  testingDiagnosticConnections = {},
  diagnosticConnectionTestResults = {},
  refreshValidationErrors
}: MCPConnectionsProps) {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newServer, setNewServer] = useState<DiagnosticMcpServer>({
    name: "",
    enabled: true,
    connectionConfig: {
      connectionType: "streamable-http",
      endpointUrl: "",
      httpHeaders: [],
      mtlsEnabled: false,
      caCert: "",
      clientCert: "",
      clientKey: ""
    }
  });
  const [isTestingNewServer, setIsTestingNewServer] = useState(false);
  const [newServerTestResult, setNewServerTestResult] = useState<"success" | "error" | null>(null);

  const handleAddDiagnostic = () => {
    // Reset new server to default values
    setNewServer({
      name: "",
      enabled: true,
      connectionConfig: {
        connectionType: "streamable-http",
        endpointUrl: "",
        httpHeaders: [],
        mtlsEnabled: false,
        caCert: "",
        clientCert: "",
        clientKey: ""
      }
    });
    setIsTestingNewServer(false);
    setNewServerTestResult(null);
    setIsAddModalOpen(true);
  };

  const handleSaveNewServer = () => {
    onUpdateDiagnosticServers([...diagnosticMcpServers, newServer]);
    setIsAddModalOpen(false);
    setIsTestingNewServer(false);
    setNewServerTestResult(null);
  };

  const handleTestNewServer = async () => {
    if (!newServer.connectionConfig.endpointUrl) {
      return;
    }

    setIsTestingNewServer(true);
    setNewServerTestResult(null);

    try {
      // Build connection config, excluding certificate fields if mTLS is disabled
      const connectionConfig: any = {
        connection_type: newServer.connectionConfig.connectionType,
        endpoint_url: newServer.connectionConfig.endpointUrl,
        http_headers: newServer.connectionConfig.httpHeaders,
        mtls_enabled: newServer.connectionConfig.mtlsEnabled
      };

      // Only include certificate fields if mTLS is enabled
      if (newServer.connectionConfig.mtlsEnabled) {
        connectionConfig.ca_cert = newServer.connectionConfig.caCert;
        connectionConfig.client_cert = newServer.connectionConfig.clientCert;
        connectionConfig.client_key = newServer.connectionConfig.clientKey;
      }

      const response = await apiClient.post('/config/test-connection', {
          enabled: newServer.enabled,
          connection_config: connectionConfig
      }
     );
      setNewServerTestResult(response.data.success ? "success" : "error");
    } catch (error) {
      console.error('New diagnostic server connection test failed:', error);
      setNewServerTestResult("error");
    } finally {
      setIsTestingNewServer(false);
    }
  };

  const updateDiagnosticServer = (index: number, server: DiagnosticMcpServer) => {
    const updatedServers = [...diagnosticMcpServers];
    updatedServers[index] = server;
    onUpdateDiagnosticServers(updatedServers);
  };

  const deleteDiagnosticServer = (index: number) => {
    const updatedServers = diagnosticMcpServers.filter((_, i) => i !== index);
    onUpdateDiagnosticServers(updatedServers);
  };
  return (
   <div>
     <Card className="box-shadow">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          MCP Connections for Observability Data
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <HelpCircle className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-white">Configure Model Context Protocol connections to observability platforms for data access</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Grafana MCP Connection */}
          <MCPConnectionItemModal
            source="grafana"
            config={mcpConnections.grafana}
            onUpdate={(config) => onUpdate({ ...mcpConnections, grafana: config })}
            onTestConnection={() => onTestConnection("grafana")}
            isTesting={testingMcpConnections.grafana}
            testResult={mcpConnectionTestResults.grafana}
            refreshValidationErrors={refreshValidationErrors}
          />

          {/* Jaeger MCP Connection */}
          <MCPConnectionItemModal
            source="jaeger"
            config={mcpConnections.jaeger}
            onUpdate={(config) => onUpdate({ ...mcpConnections, jaeger: config })}
            onTestConnection={() => onTestConnection("jaeger")}
            isTesting={testingMcpConnections.jaeger}
            testResult={mcpConnectionTestResults.jaeger}
            refreshValidationErrors={refreshValidationErrors}
          />

          {/* OpenSearch MCP Connection */}
          <MCPConnectionItemModal
            source="opensearch"
            config={mcpConnections.opensearch}
            onUpdate={(config) => onUpdate({ ...mcpConnections, opensearch: config })}
            onTestConnection={() => onTestConnection("opensearch")}
            isTesting={testingMcpConnections.opensearch}
            testResult={mcpConnectionTestResults.opensearch}
            refreshValidationErrors={refreshValidationErrors}
          />
        </div>
      </CardContent>
    </Card>

     <Card className="box-shadow mt-8">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            MCP Connections for Observability Diagnostics
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <HelpCircle className="h-4 w-4 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-white">Configure diagnostic MCP servers with optional mTLS support for secure connections</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={handleAddDiagnostic}
            className="h-9"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Diagnostic
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {diagnosticMcpServers.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No diagnostic servers configured.</p>
            <p className="text-sm mt-2">Click "Add Diagnostic" to create a new diagnostic MCP server connection.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-1 lg:grid-cols-3 gap-4">
            {diagnosticMcpServers.map((server, index) => (
              <DiagnosticMCPModal
                key={index}
                server={server}
                index={index}
                onUpdate={(updatedServer) => updateDiagnosticServer(index, updatedServer)}
                onDelete={() => deleteDiagnosticServer(index)}
                onTestConnection={onTestDiagnosticConnection ? () => onTestDiagnosticConnection(index) : undefined}
                isTesting={testingDiagnosticConnections[index]}
                testResult={diagnosticConnectionTestResults[index]}
                refreshValidationErrors={refreshValidationErrors}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>

    {/* Add Diagnostic Modal */}
    <Dialog open={isAddModalOpen} onOpenChange={setIsAddModalOpen}>
      <DialogContent className="max-h-[80vh] overflow-y-auto" style={{ width: '774px',maxHeight:"80vh" }}>
        <DialogHeader>
          <DialogTitle className="triage-journey-header">Add Diagnostic MCP Server</DialogTitle>
        </DialogHeader>
        
        <div style={{height:"60vh", overflowY:"scroll",padding:10}}>
          <DiagnosticMCPItem
          config={newServer}
          onUpdate={setNewServer}
          onTestConnection={handleTestNewServer}
          isTesting={isTestingNewServer}
          testResult={newServerTestResult}
        />
        </div>
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => setIsAddModalOpen(false)}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSaveNewServer}
            className="active-range-bg"
          >
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
   </div>
  );
}