import { useState } from "react";
import { Label } from "./../ui/label";
import { Switch } from "./../ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./../ui/select";
import { Input } from "./../ui/input";
import { Button } from "./../ui/button";
import { Plus, Trash2, CheckCircle, XCircle, Loader2, Upload, X, Download } from "lucide-react";
import { DiagnosticMcpServer } from "./../../types/config";

interface DiagnosticMCPItemProps {
  config: DiagnosticMcpServer;
  onUpdate: (config: DiagnosticMcpServer) => void;
  onTestConnection?: () => void;
  isTesting?: boolean;
  testResult?: "success" | "error" | null;
  refreshValidationErrors?: () => void;
}

export function DiagnosticMCPItem({
  config,
  onUpdate,
  onTestConnection,
  isTesting,
  testResult,
  refreshValidationErrors
}: DiagnosticMCPItemProps) {
  const [caCertFileName, setCaCertFileName] = useState<string>("");
  const [clientCertFileName, setClientCertFileName] = useState<string>("");
  const [clientKeyFileName, setClientKeyFileName] = useState<string>("");

  const addHttpHeader = () => {
    onUpdate({
      ...config,
      connectionConfig: {
        ...config.connectionConfig,
        httpHeaders: [...config.connectionConfig.httpHeaders, { key: '', value: '' }]
      }
    });
  };

  const removeHttpHeader = (index: number) => {
    onUpdate({
      ...config,
      connectionConfig: {
        ...config.connectionConfig,
        httpHeaders: config.connectionConfig.httpHeaders.filter((_, i) => i !== index)
      }
    });
  };

  const updateHttpHeader = (index: number, field: 'key' | 'value', value: string) => {
    onUpdate({
      ...config,
      connectionConfig: {
        ...config.connectionConfig,
        httpHeaders: config.connectionConfig.httpHeaders.map((header, i) =>
          i === index ? { ...header, [field]: value } : header
        )
      }
    });
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
    field: 'caCert' | 'clientCert' | 'clientKey'
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      onUpdate({
        ...config,
        connectionConfig: {
          ...config.connectionConfig,
          [field]: content
        }
      });

      // Update file name state
      if (field === 'caCert') setCaCertFileName(file.name);
      if (field === 'clientCert') setClientCertFileName(file.name);
      if (field === 'clientKey') setClientKeyFileName(file.name);
    };
    reader.readAsText(file);
  };

  const clearFile = (field: 'caCert' | 'clientCert' | 'clientKey') => {
    onUpdate({
      ...config,
      connectionConfig: {
        ...config.connectionConfig,
        [field]: ''
      }
    });

    if (field === 'caCert') setCaCertFileName('');
    if (field === 'clientCert') setClientCertFileName('');
    if (field === 'clientKey') setClientKeyFileName('');
  };

  const downloadFile = (field: 'caCert' | 'clientCert' | 'clientKey') => {
    const content = config.connectionConfig[field];
    if (!content) return;

    // Determine file name and extension
    let fileName = '';
    if (field === 'caCert') {
      fileName = caCertFileName || 'ca-certificate.pem';
    } else if (field === 'clientCert') {
      fileName = clientCertFileName || 'client-certificate.pem';
    } else if (field === 'clientKey') {
      fileName = clientKeyFileName || 'client-key.pem';
    }

    // Create blob and download
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg flex items-center justify-between bg-surface-secondary p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label htmlFor="diagnostic-switch" className="font-medium">
              Enable Diagnostic Server
            </Label>
          </div>
        </div>
        <Switch
          id="diagnostic-switch"
          checked={config.enabled}
          onCheckedChange={(checked) => {
            onUpdate({ ...config, enabled: checked });
            refreshValidationErrors?.();
          }}
        />
      </div>

      {config.enabled && (
        <div className="space-y-4 border-border">
          <div className="space-y-2">
            <Label htmlFor="diagnostic-name">Server Name *</Label>
            <Input
              id="diagnostic-name"
              placeholder="e.g., Production Diagnostics"
              value={config.name}
              onChange={(e) => onUpdate({ ...config, name: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="diagnostic-connection-type">Connection Type</Label>
            <Select value="streamable-http" disabled>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="streamable-http">HTTP Streaming</SelectItem>
              </SelectContent>
            </Select>
            <div className="text-xs text-muted-foreground">Currently only HTTP Streaming connections are supported</div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="diagnostic-endpoint">MCP Endpoint URL *</Label>
            <Input
              id="diagnostic-endpoint"
              placeholder="https://api.example.com/mcp"
              value={config.connectionConfig.endpointUrl}
              onChange={(e) =>
                onUpdate({
                  ...config,
                  connectionConfig: { ...config.connectionConfig, endpointUrl: e.target.value }
                })
              }
            />
          </div>

          {/* mTLS Configuration */}
          <div className="rounded-lg bg-surface-secondary p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <Label htmlFor="mtls-switch" className="font-medium">
                  Enable mTLS (Mutual TLS)
                </Label>
                <div className="text-xs text-muted-foreground">
                  Enable mutual TLS authentication with client certificates
                </div>
              </div>
              <Switch
                id="mtls-switch"
                checked={config.connectionConfig.mtlsEnabled}
                onCheckedChange={(checked) => {
                  // When disabling mTLS, clear all certificate fields
                  if (!checked) {
                    onUpdate({
                      ...config,
                      connectionConfig: {
                        ...config.connectionConfig,
                        mtlsEnabled: checked,
                        caCert: '',
                        clientCert: '',
                        clientKey: ''
                      }
                    });
                    // Clear file name states
                    setCaCertFileName('');
                    setClientCertFileName('');
                    setClientKeyFileName('');
                  } else {
                    onUpdate({
                      ...config,
                      connectionConfig: { ...config.connectionConfig, mtlsEnabled: checked }
                    });
                  }
                }}
              />
            </div>

            {config.connectionConfig.mtlsEnabled && (
              <div className="space-y-4 pt-2">
                {/* CA Certificate */}
                <div className="space-y-2">
                  <Label>CA Certificate</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="file"
                      accept=".pem,.crt,.cer"
                      onChange={(e) => handleFileUpload(e, 'caCert')}
                      className="hidden"
                      id="ca-cert-upload"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => document.getElementById('ca-cert-upload')?.click()}
                    >

                        <Upload className="h-4 w-4 mr-2" />
                      <span className="flex" style={{width:160}}>
                        {caCertFileName || config.connectionConfig.caCert ? 'Change File' : 'Upload CA Certificate'}
                      </span>
                    </Button>
                    {(caCertFileName || config.connectionConfig.caCert) && (
                      <>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => downloadFile('caCert')}
                          className="h-9 w-9 p-0 text-muted-foreground hover:text-blue-600"
                          title="Download CA Certificate"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => clearFile('caCert')}
                          className="h-9 w-9 p-0 text-muted-foreground hover:text-red-600"
                          title="Remove CA Certificate"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    )}


                  </div>
                  {config.connectionConfig.mtlsEnabled && (caCertFileName || config.connectionConfig.caCert) && (
                    <div className="text-xs text-green-600">
                      ✓ {caCertFileName || 'Certificate uploaded'}
                    </div>
                  )}
                </div>

                {/* Client Certificate */}
                <div className="space-y-2">
                  <Label>Client Certificate</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="file"
                      accept=".pem,.crt,.cer"
                      onChange={(e) => handleFileUpload(e, 'clientCert')}
                      className="hidden"
                      id="client-cert-upload"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => document.getElementById('client-cert-upload')?.click()}
                    >
                      <Upload className="h-4 w-4 mr-2" />
                      <span className="flex" style={{width:160}}>
                        {clientCertFileName || config.connectionConfig.clientCert ? 'Change File' : 'Upload Client Certificate'}
                      </span>
                    </Button>
                    {(clientCertFileName || config.connectionConfig.clientCert) && (
                      <>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => downloadFile('clientCert')}
                          className="h-9 w-9 p-0 text-muted-foreground hover:text-blue-600"
                          title="Download Client Certificate"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => clearFile('clientCert')}
                          className="h-9 w-9 p-0 text-muted-foreground hover:text-red-600"
                          title="Remove Client Certificate"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                  {config.connectionConfig.mtlsEnabled && (clientCertFileName || config.connectionConfig.clientCert) && (
                    <div className="text-xs text-green-600">
                      ✓ {clientCertFileName || 'Certificate uploaded'}
                    </div>
                  )}
                </div>

                {/* Client Key */}
                <div className="space-y-2">
                  <Label>Client Key</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="file"
                      accept=".pem,.key"
                      onChange={(e) => handleFileUpload(e, 'clientKey')}
                      className="hidden"
                      id="client-key-upload"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => document.getElementById('client-key-upload')?.click()}
                    >

                        <Upload className="h-4 w-4 mr-2" />
                      <span className="flex justify-start" style={{width:160}}>
                        {clientKeyFileName || config.connectionConfig.clientKey ? 'Change File' : 'Upload Client Key'}
                      </span>

                    </Button>
                    {(clientKeyFileName || config.connectionConfig.clientKey) && (
                      <>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => downloadFile('clientKey')}
                          className="h-9 w-9 p-0 text-muted-foreground hover:text-blue-600"
                          title="Download Client Key"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => clearFile('clientKey')}
                          className="h-9 w-9 p-0 text-muted-foreground hover:text-red-600"
                          title="Remove Client Key"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                  {config.connectionConfig.mtlsEnabled && (clientKeyFileName || config.connectionConfig.clientKey) && (
                    <div className="text-xs text-green-600">
                      ✓ {clientKeyFileName || 'Key uploaded'}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* HTTP Headers */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Additional HTTP Headers</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addHttpHeader}
                className="h-8"
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Header
              </Button>
            </div>

            {config.connectionConfig.httpHeaders.length > 0 && (
              <div className="space-y-3 p-3 border border-border rounded-lg bg-surface">
                {config.connectionConfig.httpHeaders.map((header, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      placeholder="Header name"
                      value={header.key}
                      onChange={(e) => updateHttpHeader(index, 'key', e.target.value)}
                      className="flex-1"
                    />
                    <Input
                      placeholder="Header value"
                      value={header.value}
                      onChange={(e) => updateHttpHeader(index, 'value', e.target.value)}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeHttpHeader(index)}
                      className="h-9 w-9 p-0 text-muted-foreground hover:text-red-600"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            <div className="text-xs text-muted-foreground">
              Optional. Add HTTP headers for authentication or custom configuration.
            </div>
          </div>

          {/* Test Connection */}
          {onTestConnection && (
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                onClick={onTestConnection}
                disabled={!config.connectionConfig.endpointUrl || isTesting}
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
          )}
        </div>
      )}
    </div>
  );
}

