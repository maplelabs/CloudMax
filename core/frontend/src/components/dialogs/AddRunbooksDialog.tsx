import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Upload, BookOpen } from 'lucide-react';
import { UploadTab } from './UploadTab';
import { ConfluenceTab } from './ConfluenceTab';
import { ErrorBoundary } from './ErrorBoundary';

interface AddRunbooksDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  confluenceConfigured: boolean;
  defaultTab?: 'upload' | 'confluence';
}

export function AddRunbooksDialog({
  open,
  onOpenChange,
  confluenceConfigured,
  defaultTab = 'upload'
}: AddRunbooksDialogProps) {
  const [activeTab, setActiveTab] = useState(defaultTab);

  function handleTabChange(value: string) {
    // Type guard to ensure only valid tab values are set
    if (value === 'upload' || value === 'confluence') {
      setActiveTab(value);
    }
  }

  function handleOpenChange(isOpen: boolean) {
    if (isOpen) {
      // Reset tab immediately when opening to prevent wrong tab from showing
      setActiveTab(defaultTab);
    }
    onOpenChange(isOpen);
  }

  function handleClose() {
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">Add Runbooks</DialogTitle>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={handleTabChange}
          className="w-full flex flex-col flex-1"
        >
          <TabsList className="w-full">
            <TabsTrigger value="upload" className="flex-1">
              <Upload className="h-4 w-4 mr-2" />
              Upload Files
            </TabsTrigger>
            <TabsTrigger value="confluence" className="flex-1">
              <BookOpen className="h-4 w-4 mr-2" />
              Confluence
            </TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="mt-4 flex-1">
            <ErrorBoundary>
              <UploadTab onClose={handleClose} />
            </ErrorBoundary>
          </TabsContent>

          <TabsContent value="confluence" className="mt-4 flex-1">
            <ErrorBoundary>
              <ConfluenceTab
                confluenceConfigured={confluenceConfigured}
                onClose={handleClose}
              />
            </ErrorBoundary>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
