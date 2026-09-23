import { useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Checkbox } from '../ui/checkbox';
import { DialogFooter } from '../ui/dialog';
import { Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import { useImportConfluence } from '../../hooks/useRunbooks';
import { useNavigate } from 'react-router-dom';
import type { ConfluenceImportedPage } from '../../types/runbooks';

const DEFAULT_MAX_DEPTH = 10;
const DEFAULT_MAX_PAGES = 50;
const MIN_DEPTH = 1;
const MAX_DEPTH_LIMIT = 20;
const MIN_PAGES = 1;
const MAX_PAGES_LIMIT = 100;

interface ConfluenceTabProps {
  confluenceConfigured: boolean;
  onClose: () => void;
}

interface ImportFormData {
  page_url: string;
  include_children: boolean;
  max_depth: number;
  max_pages: number;
}

const INITIAL_FORM_STATE: ImportFormData = {
  page_url: '',
  include_children: false,
  max_depth: DEFAULT_MAX_DEPTH,
  max_pages: DEFAULT_MAX_PAGES,
};

type ImportStep = 'import' | 'results';

export function ConfluenceTab({
  confluenceConfigured,
  onClose,
}: ConfluenceTabProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<ImportStep>('import');
  const [formData, setFormData] = useState<ImportFormData>(INITIAL_FORM_STATE);
  const [importResults, setImportResults] = useState<any>(null);

  const importMutation = useImportConfluence();

  // Consolidated status configuration
  const statusConfig = {
    success: {
      style: 'bg-emerald-50 border-emerald-200',
      icon: <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />,
      message: 'Successfully imported',
    },
    updated: {
      style: 'bg-blue-50 border-blue-200',
      icon: <CheckCircle2 className="h-4 w-4 text-blue-600 flex-shrink-0" />,
      message: 'Updated existing runbook',
    },
    error: {
      style: 'bg-red-50 border-red-200',
      icon: <XCircle className="h-4 w-4 text-danger flex-shrink-0" />,
      message: (page: ConfluenceImportedPage) => page.error || 'Import failed',
    },
  } as const;

  async function handleImport() {
    const result = await importMutation.mutateAsync(formData as any);
    setImportResults(result);
    setStep('results');
  }

  function handleClose() {
    setStep('import');
    setFormData(INITIAL_FORM_STATE);
    setImportResults(null);
    importMutation.reset();
    onClose();
  }

  function handleGoToSetup() {
    onClose();
    navigate('/setup?tab=integrations');
  }

  function getPageStatusStyles(status: string): string {
    return statusConfig[status as keyof typeof statusConfig]?.style || '';
  }

  function getPageStatusIcon(status: string) {
    // Small icons (h-4) for inline status indicators in compact lists
    return statusConfig[status as keyof typeof statusConfig]?.icon || null;
  }

  function getPageStatusMessage(page: ConfluenceImportedPage): string {
    const config = statusConfig[page.status as keyof typeof statusConfig];
    if (!config) return '';
    return typeof config.message === 'function' ? config.message(page) : config.message;
  }

  if (!confluenceConfigured) {
    return (
      <>
        <div className="flex flex-col items-center gap-4 py-8">
          {/* Large icon (h-12) for empty/warning state - draws attention */}
          <AlertCircle className="h-12 w-12 text-amber-500" />
          <div className="text-center space-y-2">
            <h3 className="font-semibold text-foreground">Confluence is not configured</h3>
            <p className="text-sm text-muted-foreground">
              To import from Confluence, you need to configure your Confluence connection first.
            </p>
          </div>
          <Button onClick={handleGoToSetup} className="mt-2 active-range-bg text-white">
            Go to Setup →
          </Button>
        </div>

        <DialogFooter className="pt-4">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </>
    );
  }

  function renderImportStep() {
    const isImportDisabled = !formData.page_url || importMutation.isPending;

    return (
      <>
        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Import documentation from Confluence into your runbook library
          </p>

          <div className="space-y-2">
            <Label htmlFor="page_url">Confluence Page URL *</Label>
            <Input
              id="page_url"
              type="url"
              placeholder="https://company.atlassian.net/wiki/..."
              value={formData.page_url}
              onChange={(e) => setFormData({ ...formData, page_url: e.target.value })}
            />
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="include_children"
              checked={formData.include_children}
              onCheckedChange={(checked) =>
                setFormData({ ...formData, include_children: checked as boolean })
              }
            />
            <Label htmlFor="include_children" className="text-sm font-normal cursor-pointer">
              Include child pages (recursive)
            </Label>
          </div>

          {formData.include_children && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="max_depth">Maximum Depth</Label>
                <Input
                  id="max_depth"
                  type="number"
                  min={MIN_DEPTH}
                  max={MAX_DEPTH_LIMIT}
                  value={formData.max_depth}
                  onChange={(e) => setFormData({
                    ...formData,
                    max_depth: parseInt(e.target.value) || DEFAULT_MAX_DEPTH
                  })}
                />
                <p className="text-xs text-muted-foreground">
                  How many levels deep to fetch child pages ({MIN_DEPTH}-{MAX_DEPTH_LIMIT})
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="max_pages">Maximum Pages</Label>
                <Input
                  id="max_pages"
                  type="number"
                  min={MIN_PAGES}
                  max={MAX_PAGES_LIMIT}
                  value={formData.max_pages}
                  onChange={(e) => setFormData({
                    ...formData,
                    max_pages: parseInt(e.target.value) || DEFAULT_MAX_PAGES
                  })}
                />
                <p className="text-xs text-muted-foreground">
                  Maximum total pages to import ({MIN_PAGES}-{MAX_PAGES_LIMIT})
                </p>
              </div>
            </div>
          )}

          {importMutation.isError && (
            <div className="flex items-center gap-2 text-sm text-danger bg-red-50 p-3 rounded-md border border-red-200">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>
                {importMutation.error instanceof Error
                  ? importMutation.error.message
                  : 'Failed to import from Confluence'}
              </span>
            </div>
          )}
        </div>

        <DialogFooter className="pt-4">
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleImport}
            disabled={isImportDisabled}
            className="active-range-bg text-white"
          >
            {importMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Import
          </Button>
        </DialogFooter>
      </>
    );
  }

  function renderResultsStep() {
    if (!importResults) return null;

    const allPages = [importResults.parent_page, ...importResults.child_pages];

    return (
      <>
        <div className="space-y-4">
          <div>
            <h3 className="text-base font-semibold text-foreground">Import Complete</h3>
            <p className="text-sm text-muted-foreground">
              Imported {importResults.total_imported} of {allPages.length} pages
            </p>
          </div>

          <div className="max-h-96 overflow-y-auto space-y-2">
            {allPages.map((page: ConfluenceImportedPage, index: number) => (
              <div
                key={`${page.page_id}-${index}`}
                className={`flex items-start gap-3 p-3 rounded-md border ${getPageStatusStyles(page.status)}`}
              >
                {getPageStatusIcon(page.status)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{page.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {getPageStatusMessage(page)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <DialogFooter className="pt-4">
          <Button onClick={handleClose} className="active-range-bg text-white">
            Done
          </Button>
        </DialogFooter>
      </>
    );
  }

  if (step === 'results') {
    return renderResultsStep();
  }

  return renderImportStep();
}
