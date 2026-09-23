import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { DialogFooter } from '../ui/dialog';
import { Upload, AlertCircle, CheckCircle, Loader2, X } from 'lucide-react';
import { useUploadRunbook, formatFileSize } from '../../hooks/useRunbooks';
import { toast } from 'sonner';

interface UploadTabProps {
  onClose: () => void;
}

type UploadStep = 'select' | 'confirm' | 'success';

const MAX_FILE_SIZE = 5 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = ['.md'];

export function UploadTab({ onClose }: UploadTabProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState<UploadStep>('select');
  const [uploadSuccessCount, setUploadSuccessCount] = useState(0);

  const uploadRunbookMutation = useUploadRunbook();

  // Cleanup files on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      setFiles([]);
    };
  }, []);

  function validateFile(file: File): string | null {
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();

    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      return `Invalid file type: ${file.name}. Only .md files are allowed.`;
    }

    if (file.size > MAX_FILE_SIZE) {
      return `File size too large: ${file.name} (${formatFileSize(file.size)}). Maximum size is 5MB.`;
    }

    return null;
  }

  function handleFiles(selectedFiles: FileList | null) {
    if (!selectedFiles || selectedFiles.length === 0) return;

    const fileArray = Array.from(selectedFiles);

    for (const file of fileArray) {
      const error = validateFile(file);
      if (error) {
        setUploadError(error);
        return;
      }
    }

    setUploadError('');
    setFiles(fileArray);
    setUploadStep('confirm');
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    handleFiles(e.target.files);
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    handleFiles(e.dataTransfer.files);
  }

  function removeFile(index: number) {
    const newFiles = files.filter((_, i) => i !== index);
    setFiles(newFiles);

    if (newFiles.length === 0) {
      setUploadStep('select');
    }
  }

  async function handleUpload() {
    if (files.length === 0) return;

    setIsUploading(true);
    setUploadError('');

    try {
      const formData = new FormData();
      files.forEach((file) => formData.append('files', file));

      const result = await uploadRunbookMutation.mutateAsync({ formData });

      const successCount = result.successful_uploads || 0;
      const failedCount = result.failed_uploads || 0;
      const skippedCount = result.skipped_files || 0;

      if (failedCount > 0) {
        const failedFiles = result.file_results
          ?.filter((r: any) => r.status === 'failed')
          .map((r: any) => r.filename)
          .join(', ');
        toast.error(`Failed to upload ${failedCount} file(s): ${failedFiles}`);
      }

      if (skippedCount > 0) {
        const skippedFiles = result.file_results
          ?.filter((r: any) => r.status === 'skipped')
          .map((r: any) => r.filename)
          .join(', ');
        toast.warning(`Skipped ${skippedCount} file(s): ${skippedFiles}`);
      }

      if (successCount > 0) {
        setUploadSuccessCount(successCount);
        setUploadStep('success');
        toast.success(`Successfully uploaded ${successCount} runbook(s)`);
      } else {
        handleCloseUpload();
      }
    } catch (error) {
      console.error('Failed to upload runbook:', error);
      toast.error('Failed to upload runbook(s). Please try again.');
      setUploadError('Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  }

  function handleCloseUpload() {
    setFiles([]);
    setUploadError('');
    setUploadStep('select');
    setUploadSuccessCount(0);
    onClose();
  }

  const totalSize = files.reduce((sum, file) => sum + file.size, 0);
  const isUploadDisabled = isUploading || files.length === 0 || uploadRunbookMutation.isPending;

  function renderFileUploadArea() {
    const isDisabled = uploadStep === 'confirm';

    return (
      <div
        onDragOver={uploadStep === 'select' ? handleDragOver : undefined}
        onDrop={uploadStep === 'select' ? handleDrop : undefined}
        className={`border ${isDisabled ? '' : 'border-2 border-dashed border-blue-300 hover:border-blue-400 cursor-pointer'} rounded-md p-12 text-center bg-blue-50/30 transition-colors ${isDisabled ? 'opacity-50' : ''}`}
      >
        <Input
          id="file-upload"
          type="file"
          accept=".md"
          multiple
          onChange={handleFileChange}
          className="hidden"
          disabled={isDisabled}
          aria-label="Upload markdown runbook files"
          aria-describedby="file-upload-description"
        />
        <label htmlFor="file-upload" className={isDisabled ? '' : 'cursor-pointer'}>
          <div className="flex flex-col items-center gap-4">
            <Upload className="h-12 w-12 text-gray-400" />
            <div className="space-y-2">
              <p className="text-base font-medium text-foreground">Drag & drop files here</p>
              <p className="text-sm text-muted-foreground">or</p>
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={isDisabled}
              className="pointer-events-none font-medium"
            >
              Browse Files
            </Button>
            <p id="file-upload-description" className="text-sm text-muted-foreground mt-2">
              Supported format: .md (Max 5MB each)
            </p>
          </div>
        </label>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="space-y-6 flex-1">
        <p className="text-sm text-muted-foreground">
          Upload one or more Markdown (.md) files to add to your runbook library
        </p>

        {uploadStep !== 'success' && renderFileUploadArea()}

        {uploadStep === 'confirm' && (
          <>
            <div className="space-y-2">
              {files.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 border rounded-md bg-surface hover:bg-surface-hover transition-colors"
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Upload className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="text-sm font-medium truncate">{file.name}</span>
                    <span className="text-sm text-muted-foreground flex-shrink-0">
                      {formatFileSize(file.size)}
                    </span>
                  </div>
                  <button
                    onClick={() => removeFile(index)}
                    className="ml-2 text-muted-foreground hover:text-danger transition-colors"
                    disabled={isUploading}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            <p className="text-sm text-muted-foreground">
              {files.length} file{files.length !== 1 ? 's' : ''} selected ({formatFileSize(totalSize)} total)
            </p>
          </>
        )}

        {uploadStep === 'success' && (
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <div className="rounded-full bg-green-50 p-4">
              <CheckCircle className="h-12 w-12 text-success" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-semibold text-foreground">Upload Successful!</h3>
              <p className="text-sm text-muted-foreground">
                {uploadSuccessCount} runbook{uploadSuccessCount !== 1 ? 's' : ''} uploaded successfully
              </p>
            </div>
          </div>
        )}

        {uploadError && (
          <div className="flex items-center gap-2 text-sm text-danger bg-red-50 p-3 rounded-md border border-red-200">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            {uploadError}
          </div>
        )}
      </div>

      <DialogFooter className="pt-4">
        {uploadStep === 'success' ? (
          <Button onClick={handleCloseUpload} className="active-range-bg text-white">
            Done
          </Button>
        ) : (
          <>
            <Button variant="outline" onClick={handleCloseUpload}>
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={isUploadDisabled}
              className="active-range-bg text-white"
            >
              {isUploading || uploadRunbookMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                'Upload'
              )}
            </Button>
          </>
        )}
      </DialogFooter>
    </div>
  );
}
