import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "./../ui/dialog";
import { Button } from "./../ui/button";
import { Card, CardHeader, CardTitle } from "./../ui/card";
import { SecondaryLLMConfiguration } from "./SecondaryLLMConfiguration";
import { SetupConfig } from "./../../types/config";
import { ChevronDown, ChevronRight } from "lucide-react";

interface SecondaryLLMConfigurationModalProps {
  secondaryLlmConfig: NonNullable<SetupConfig["customDeployment"]>["secondaryLlm"];
  onUpdate: (secondaryLlmConfig: NonNullable<SetupConfig["customDeployment"]>["secondaryLlm"]) => void;
}

export function SecondaryLLMConfigurationModal({ secondaryLlmConfig, onUpdate }: SecondaryLLMConfigurationModalProps) {
  const [open, setOpen] = useState(false);
  const [tempConfig, setTempConfig] = useState(secondaryLlmConfig);

  const handleOpen = (isOpen: boolean) => {
    if (isOpen) {
      // When opening, set temp config to current config
      setTempConfig(secondaryLlmConfig);
    }
    setOpen(isOpen);
  };

  const handleSave = () => {
    onUpdate(tempConfig);
    setOpen(false);
  };

  const handleCancel = () => {
    setTempConfig(secondaryLlmConfig);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogTrigger asChild>
        <Card className="box-shadow cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="flex flex-row items-center justify-between py-4">
            <CardTitle className="">Secondary LLM Configuration</CardTitle>
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
          <DialogTitle className="triage-journey-header">Secondary LLM Configuration</DialogTitle>
          <DialogDescription>
            Configure a secondary Large Language Model for fallback or specialized tasks.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <SecondaryLLMConfiguration
            secondaryLlmConfig={tempConfig}
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
