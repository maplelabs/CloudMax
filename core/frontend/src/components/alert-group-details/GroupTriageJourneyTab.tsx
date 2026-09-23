import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Clock } from "lucide-react";
import { MarkdownContent } from "../alert-details/MarkdownContent";
import { StarIcon } from "../../icons";
import { Button } from "../ui/button";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";

interface GroupTriageJourneyTabProps {
  journey?: any[] | null;
  triageStatus: string;
  updatedAt: string;
}

export function GroupTriageJourneyTab({ journey, triageStatus, updatedAt }: GroupTriageJourneyTabProps) {
  const [openToolModal, setOpenToolModal] = useState<number | null>(null);

  if (!journey || journey.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="max-w-md mx-auto">
          <div className="mb-4">
            <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
              <Clock className="h-6 w-6 text-muted" />
            </div>
          </div>
          <h3 className="text-lg font-medium text-foreground mb-2">No Triage Data</h3>
          <p className="text-secondary">
            No triage journey data available for this alert group.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Card className="bg-card" style={{ boxShadow: "0px 4px 6px 0px #0000000D" }}>
        <CardHeader>
          <CardTitle className="triage-journey-header">Triage Journey</CardTitle>
        </CardHeader>
        <CardContent>
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

            {journey.map((message: any, index: number) => (
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
                    <div className="space-y-2 flex items-center justify-space-between">
                      <Button
                        onClick={() => setOpenToolModal(index)}
                        className="flex items-center gap-2 py-2 rounded-sm text-sm hover:opacity-80 transition-opacity"
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
        </CardContent>
      </Card>

      {/* Tool Execution Details Modal */}
      {openToolModal !== null && journey[openToolModal] && (
        <Dialog open={true} onOpenChange={(open) => !open && setOpenToolModal(null)}>
          <DialogContent style={{ width: '774px' }}>
            <DialogHeader>
              <DialogTitle className="triage-journey-header">Tool Execution Details</DialogTitle>
            </DialogHeader>
            <div className="space-y-6 overflow-y-auto pr-2" style={{ maxHeight: 'calc(100vh - 100px)' }}>
              {/* Arguments Section */}
              {journey[openToolModal].tool_args && (
                <div>
                  <h3 className="triage-journey-label">Arguments</h3>
                  <div className="bg-surface border rounded-lg p-4">
                    <pre className="text-sm font-mono whitespace-pre-wrap break-words text-foreground">
                      {(() => {
                        try {
                          const parsed = JSON.parse(journey[openToolModal].tool_args);
                          return JSON.stringify(parsed, null, 2);
                        } catch {
                          return journey[openToolModal].tool_args;
                        }
                      })()}
                    </pre>
                  </div>
                </div>
              )}

              {/* Response Section */}
              {journey[openToolModal].tool_response && (
                <div>
                  <h3 className="triage-journey-label">Response</h3>
                  <div className="bg-surface border rounded-lg p-4">
                    <pre className="text-sm font-mono whitespace-pre-wrap break-words text-foreground">
                      {(() => {
                        try {
                          const parsed = JSON.parse(journey[openToolModal].tool_response);
                          return JSON.stringify(parsed, null, 2);
                        } catch {
                          return journey[openToolModal].tool_response;
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
}
