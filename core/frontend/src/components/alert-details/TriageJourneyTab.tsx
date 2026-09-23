import { useState } from "react";
import { RefreshCw, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";
import { MarkdownContent } from "./MarkdownContent";
import { StarIcon } from "../../icons";

interface TriageJourneyTabProps {
  alert: any;
  triage: any;
  triageLoading: boolean;
  refreshingTab: string | null;
  handleTriageRefresh: () => void;
}

export const TriageJourneyTab = ({ alert, triage, triageLoading, refreshingTab, handleTriageRefresh }: TriageJourneyTabProps) => {
  const [openToolModal, setOpenToolModal] = useState<number | null>(null);
  const isToolModalOpen = openToolModal !== null;

  return (
    <div className="pb-6">
      <Card className="rounded-lg mr-2 bg-surface">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="card-title">Triage Journey</CardTitle>
          {alert.triage_status === "processing" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleTriageRefresh}
              disabled={refreshingTab === 'triage-journey'}
              className="gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${refreshingTab === 'triage-journey' ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {triageLoading ? (
            <div className="text-center py-16">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-muted" />
              <p className="text-secondary">Loading triage journey...</p>
            </div>
          ) : alert.triage_status === "pending" || alert.triage_status === "not-started" ? (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <Clock className="h-6 w-6 text-muted" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Triage Not Started</h3>
                <p className="text-secondary">
                  Triage analysis has not been started for this alert. Please start triage from the alerts page.
                </p>
              </div>
            </div>
          ) : triage && triage.messages ? (
            <div className="relative">
              {/* Continuous vertical line */}
              <div
                className="absolute"
                style={{
                  left: '5.5px',
                  top: '8px',
                  bottom: '0',
                  width: '1px',
                  background:"#90ccb8"
                }}
              />

              {triage.messages.map((message: any, index: number) => (
                <div key={index} className="relative flex gap-4 mb-6 last:mb-0">
                  {/* Timeline dot */}
                  <div className="absolute left-0 top-2">
                    <div className="w-3 h-3 rounded-full bg-success z-10" style={{ position: 'relative' }} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 bg-card box-shadow rounded-lg p-4 space-y-3 ml-6">
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <h4 className="text-foreground" style={{
                        fontWeight: 700,
                        fontSize: '15px',
                        lineHeight: '24px',
                        letterSpacing: '-0.31px'
                      }}>{message.agent_name}</h4>
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(message.timestamp).toLocaleString()}
                      </span>
                    </div>

                    {/* Message content */}
                    {message.content && (
                      <div className="text-sm text-secondary leading-relaxed flex items-start gap-2">
                        <StarIcon/>
                        <div className="flex-1">
                          <MarkdownContent content={message.content} />
                        </div>
                      </div>
                    )}

                    {/* Tool execution */}
                    {message.tool_name && (
                      <div className="space-y-2 flex items-center justify-space-between ">
                        <Button
                          onClick={() => setOpenToolModal(index)}
                          className="flex items-center gap-2  py-2 rounded-sm text-sm hover:opacity-80 transition-opacity"
                        >
                          <span className="font-medium bg-primary px-3 py-2 rounded-lg text-white">
                            View tool execution details
                          </span>
                          
                        </Button>
                        <span className="text-xs font-medium px-2">
                            Tool used: <span className="font-mono">{message.tool_name}</span>
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <Clock className="h-6 w-6 text-muted" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">No Triage Data</h3>
                <p className="text-secondary">
                  No triage journey data available for this alert.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tool Execution Details Modal */}
      {isToolModalOpen && triage?.messages[openToolModal] && (
        <Dialog open={isToolModalOpen} onOpenChange={(open) => { if (!open) setOpenToolModal(null); }}>
          <DialogContent style={{ width: '774px' }}>
            <DialogHeader>
              <DialogTitle className="triage-journey-header">Tool Execution Details</DialogTitle>
            </DialogHeader>
            <div className="space-y-6 overflow-y-auto pr-2" style={{ maxHeight: 'calc(100vh - 100px)' }}>
              {/* Arguments Section */}
              {triage.messages[openToolModal].tool_args && (
                <div>
                  <h3 className="triage-journey-label">Arguments</h3>
                  <div className="bg-surface border rounded-lg p-4">
                    <pre className="text-sm font-mono whitespace-pre-wrap break-words text-foreground">
                      {(() => {
                        try {
                          const parsed = JSON.parse(triage.messages[openToolModal].tool_args);
                          return JSON.stringify(parsed, null, 2);
                        } catch {
                          return triage.messages[openToolModal].tool_args;
                        }
                      })()}
                    </pre>
                  </div>
                </div>
              )}

              {/* Response Section */}
              {triage.messages[openToolModal].tool_response && (
                <div>
                  <h3 className="triage-journey-label">Response</h3>
                  <div className="bg-surface border rounded-lg p-4">
                    <pre className="text-sm font-mono whitespace-pre-wrap break-words text-foreground">
                      {(() => {
                        try {
                          const parsed = JSON.parse(triage.messages[openToolModal].tool_response);
                          return JSON.stringify(parsed, null, 2);
                        } catch {
                          return triage.messages[openToolModal].tool_response;
                        }
                      })()}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};
