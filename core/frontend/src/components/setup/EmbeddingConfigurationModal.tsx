import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "./../ui/dialog";
import { Button } from "./../ui/button";
import { Card, CardHeader, CardTitle } from "./../ui/card";
import { EmbeddingConfiguration } from "./EmbeddingConfiguration";
import { SetupConfig } from "./../../types/config";
import { ChevronDown, ChevronRight } from "lucide-react";

interface EmbeddingConfigurationModalProps {
  embeddingConfig: NonNullable<SetupConfig["customDeployment"]>["embedding"];
  onUpdate: (embeddingConfig: NonNullable<SetupConfig["customDeployment"]>["embedding"]) => void;
}

export function EmbeddingConfigurationModal({ embeddingConfig, onUpdate }: EmbeddingConfigurationModalProps) {
  const [open, setOpen] = useState(false);
  const [tempConfig, setTempConfig] = useState(embeddingConfig);

  const handleOpen = (isOpen: boolean) => {
    if (isOpen) {
      // When opening, set temp config to current config
      setTempConfig(embeddingConfig);
    }
    setOpen(isOpen);
  };

  const handleSave = () => {
    onUpdate(tempConfig);
    setOpen(false);
  };

  const handleCancel = () => {
    setTempConfig(embeddingConfig);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogTrigger asChild>
        <Card className="box-shadow cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="flex flex-row items-center justify-between py-4">
            <CardTitle className="">Embedding Configuration</CardTitle>
            <Button
              variant="ghost"
              size="sm"
            >
              {true ? (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </Button>
          </CardHeader>
        </Card>
      </DialogTrigger>
      <DialogContent className=" max-h-[90vh] overflow-y-auto" style={{ width: '774px' }}>
        <DialogHeader>
          <DialogTitle className="triage-journey-header">Embedding Configuration</DialogTitle>
          <DialogDescription>
            Configure the embedding model for semantic search and analysis.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <EmbeddingConfiguration
            embeddingConfig={tempConfig}
            onUpdate={setTempConfig}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button className="active-range-bg" onClick={handleSave}>
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
