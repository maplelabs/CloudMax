import { useState } from "react";
import { Code2, ChevronRight, FileText, DatabaseIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";

interface TechnicalDetailsCardProps {
  alert: any;
}

export const TechnicalDetailsCard = ({ alert }: TechnicalDetailsCardProps) => {
  const [openModal, setOpenModal] = useState<string | null>(null);

  return (
    <>
      <Card className="box-shadow rounded-lg mr-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 info-title-text">
            <FileText size={12}/>
            Technical Details
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {/* Annotations Card */}
            <button
              onClick={() => setOpenModal('annotations')}
              className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-surface-secondary/50 transition-colors cursor-pointer text-left box-shadow"
            >
              <div className="flex items-center gap-3">
                <div className="p-4 bg-info-light rounded-lg flex items-center justify-center">
                  <Code2 className="h-5 w-5 text-info" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Annotations</h4>
                  <p className="text-sm text-muted-foreground">View annotation details</p>
                </div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
            </button>

            {/* Raw Alert Payload Card */}
            <button
              onClick={() => setOpenModal('raw-payload')}
              className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-surface-secondary/50 transition-colors cursor-pointer text-left box-shadow"
            >
              <div className="flex items-center gap-3">
                <div className="p-4 bg-purple-light rounded-lg flex items-center justify-center">
                  <DatabaseIcon className="h-5 w-5 text-purple" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">Raw Alert Payload</h4>
                  <p className="text-sm text-muted-foreground">View complete payload data</p>
                </div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Annotations Modal */}
      <Dialog open={openModal === 'annotations'} onOpenChange={(open) => !open && setOpenModal(null)}>
        <DialogContent className="max-h-[80vh]" style={{ width: '774px' }}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 triage-journey-header">
              <div className="p-4 bg-info-light rounded-lg flex items-center justify-center">
                  <Code2 className="h-5 w-5 text-info" />
                </div>
              Annotations
            </DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto max-h-[60vh]">
            <pre className="p-4 bg-surface-secondary rounded text-sm font-mono overflow-x-auto">
              {JSON.stringify(alert.payload?.annotations || {}, null, 2)}
            </pre>
          </div>
        </DialogContent>
      </Dialog>

      {/* Raw Payload Modal */}
      <Dialog open={openModal === 'raw-payload'} onOpenChange={(open) => !open && setOpenModal(null)}>
        <DialogContent className="max-w-4xl max-h-[80vh]" style={{ width: '774px' }}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 triage-journey-header">
              <div className="p-4 bg-purple-light rounded-lg flex items-center justify-center">
                  <DatabaseIcon className="h-5 w-5 text-purple" />
              </div>
              Raw Alert Payload
            </DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto max-h-[60vh]">
            <pre className="p-4 bg-surface-secondary rounded text-sm font-mono overflow-x-auto whitespace-pre">
              {JSON.stringify(alert.payload, null, 2)}
            </pre>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};
