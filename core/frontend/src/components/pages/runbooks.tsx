import { useState, useEffect } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Checkbox } from "../ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "../ui/table";
import { Card } from "../ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../ui/alert-dialog";
import {
  Eye,
  Trash2,
  FileText,
  AlertCircle,
  Loader2,
  Plus
} from "lucide-react";
import { cn } from "../ui/utils";
import { useRunbooks, useDeleteRunbook, useBulkDeleteRunbooks, formatFileSize } from "../../hooks/useRunbooks";
import { useDebounce } from "../../hooks/useDebounce";
import { useConfig } from "../../hooks/useConfig";
import { SearchInput } from "../runbooks/SearchInput";
import { Runbook } from "../../types/runbooks";
import { toast } from "sonner";
import { AddRunbooksDialog } from "../dialogs/AddRunbooksDialog";

// Legacy interface for compatibility with existing components
export interface LegacyRunbook {
  id: string;
  title: string;
  source: 'file' | 'confluence';
  lastUpdated: string;
  size?: number;
  content: string;
}

interface RunbooksProps {
  onViewRunbook: (runbook: LegacyRunbook) => void;
}

export function Runbooks({ onViewRunbook }: RunbooksProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(10);
  const [searchTerm, setSearchTerm] = useState("");
  const [semanticSearchEnabled, setSemanticSearchEnabled] = useState(false);
  const debouncedSearchTerm = useDebounce(searchTerm, 300);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [deletingRunbookId, setDeletingRunbookId] = useState<string | null>(null);

  // Unified Add Runbooks dialog state
  const [isAddRunbooksDialogOpen, setIsAddRunbooksDialogOpen] = useState(false);

  // Bulk delete state
  const [selectedRunbookIds, setSelectedRunbookIds] = useState<Set<string>>(new Set());
  const bulkDeleteMutation = useBulkDeleteRunbooks();

  // Check if Confluence is configured using the existing useConfig hook
  const { config: appConfig} = useConfig();

  const confluenceConfigured = Boolean(
    appConfig?.external_runbook_config?.confluence?.enabled
  );

  // Use React Query hooks
  const deleteRunbookMutation = useDeleteRunbook();

  // Use React Query hook to fetch runbooks with search
  const {
    data: runbooksResponse,
    isLoading,
    isError,
    error,
    refetch
  } = useRunbooks({
    page: currentPage,
    page_size: pageSize,
    search: debouncedSearchTerm,
    semantic_search: semanticSearchEnabled && !!debouncedSearchTerm
  });

  // Convert API runbooks to legacy format for compatibility
  const convertToLegacyFormat = (apiRunbook: Runbook): LegacyRunbook => {
    return {
      id: apiRunbook.id,
      title: apiRunbook.name,
      source: apiRunbook.source_type,
      lastUpdated: apiRunbook.updated_at,
      size: apiRunbook.content_size_bytes,
      content: "" // Content not provided in list view, loaded on detail view
    };
  };

  const paginatedRunbooks = runbooksResponse?.runbooks?.map(convertToLegacyFormat) || [];
  const totalItems = runbooksResponse?.pagination?.total_items || 0;

  // Reset to page 1 when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearchTerm, semanticSearchEnabled]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const datePart = date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
    const timePart = date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit'
    });
    return `${datePart} at ${timePart}`;
  };

  const formatSource = (source: string) => {
    // Return source type as-is with proper capitalization
    const sourceMap: Record<string, string> = {
      'file': 'File',
      'confluence': 'Confluence'
    };
    return sourceMap[source] || source;
  };

  const isRunbookSelected = (id: string) => selectedRunbookIds.has(id);

  function toggleRunbookSelection(id: string) {
    setSelectedRunbookIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedRunbookIds.size > 0) {
      setSelectedRunbookIds(new Set());
    } else {
      setSelectedRunbookIds(new Set(paginatedRunbooks.map(r => r.id)));
    }
  }

  useEffect(() => {
    setSelectedRunbookIds(new Set());
  }, [currentPage, debouncedSearchTerm]);

  async function handleBulkDelete() {
    try {
      const result = await bulkDeleteMutation.mutateAsync(Array.from(selectedRunbookIds));

      if (result.successful_deletes > 0) {
        toast.success(`Successfully deleted ${result.successful_deletes} runbook(s)`);
      }

      if (result.failed_deletes > 0) {
        const failedResults = result.results.filter(r => r.status === 'error');
        const errorCount = failedResults.length;
        const displayCount = Math.min(errorCount, 5);
        const errorMessages = failedResults
          .slice(0, displayCount)
          .map(r => `• ${r.runbook_title}: ${r.error_message}`)
          .join('\n');

        const additionalErrors = errorCount > displayCount
          ? `\n...and ${errorCount - displayCount} more`
          : '';

        toast.error(
          `Failed to delete ${result.failed_deletes} runbook(s):\n${errorMessages}${additionalErrors}`,
          { duration: 8000 }
        );
      }

      // Clear all selections after bulk delete (regardless of success/failure)
      // This prevents confusion from keeping selections that may be on different pages
      setSelectedRunbookIds(new Set());
      setDeleteConfirmationText("");

    } catch (error) {
      console.error('Bulk delete failed:', error);
      toast.error('Bulk delete operation failed. Please try again.');
      // Clear selection even on error to avoid stale state
      setSelectedRunbookIds(new Set());
    }
  }

  const handleDelete = async (runbook: LegacyRunbook) => {
    setDeletingRunbookId(runbook.id);
    try {
      await deleteRunbookMutation.mutateAsync(runbook.id);
      toast.success(`Runbook "${runbook.title}" deleted successfully`);
      setRunbookToDelete(null);
      setDeleteConfirmationText("");
    } catch (error) {
      console.error('Failed to delete runbook:', error);
      toast.error(`Failed to delete runbook "${runbook.title}". Please try again.`);
    } finally {
      setDeletingRunbookId(null);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="page-title font-bold title-lg-header">Runbooks</h1>
        <div className="flex items-center gap-2">
          {/* Bulk Delete Button - Only show when items are selected */}
          {selectedRunbookIds.size > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="gap-2">
                  <Trash2 className="h-4 w-4" />
                  Delete Selected ({selectedRunbookIds.size})
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete {selectedRunbookIds.size} Runbook(s)</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete {selectedRunbookIds.size} runbook(s). This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <div className="py-4">
                  <Label htmlFor="bulk-delete-confirmation">
                    Type "delete" to confirm:
                  </Label>
                  <Input
                    id="bulk-delete-confirmation"
                    value={deleteConfirmationText}
                    onChange={(e) => setDeleteConfirmationText(e.target.value)}
                    placeholder="delete"
                    className="mt-2"
                  />
                </div>
                <AlertDialogFooter>
                  <AlertDialogCancel onClick={() => setDeleteConfirmationText("")}>
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-red-600 hover:bg-red-700"
                    disabled={deleteConfirmationText !== "delete" || bulkDeleteMutation.isPending}
                    onClick={(e) => {
                      e.preventDefault();
                      if (deleteConfirmationText === "delete") {
                        handleBulkDelete();
                      }
                    }}
                  >
                    {bulkDeleteMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Deleting...
                      </>
                    ) : (
                      "Delete"
                    )}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}

          <Button
            className="gap-2 text-white active-range-bg"
            onClick={() => setIsAddRunbooksDialogOpen(true)}
          >
            <Plus className="h-4 w-4" />
            Add Runbooks
          </Button>
        </div>
      </div>

      {/* Add Runbooks Dialog */}
      <AddRunbooksDialog
        open={isAddRunbooksDialogOpen}
        onOpenChange={setIsAddRunbooksDialogOpen}
        confluenceConfigured={confluenceConfigured}
      />

      {/* Search and Filter Bar */}
      <div className="py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center w-full">
          <div className="w-full sm:w-96">
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              semanticSearchEnabled={semanticSearchEnabled}
              onSemanticSearchToggle={() => setSemanticSearchEnabled(!semanticSearchEnabled)}
              placeholder="Search runbooks by title, content, or description..."

            />
            </div>

            <div className="text-sm text-muted-foreground whitespace-nowrap">
              {totalItems} runbook{totalItems !== 1 ? 's' : ''} found
            </div>
          </div>

          {/* <div className="flex items-center gap-3">
            <Select
              value={pageSize.toString()}
              onValueChange={(value: string) => {
                setPageSize(parseInt(value));
                setCurrentPage(1);
              }}
            >
              <SelectTrigger className="w-36 h-10">
                <SelectValue placeholder="Items per page" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="5">5 per page</SelectItem>
                <SelectItem value="10">10 per page</SelectItem>
                <SelectItem value="25">25 per page</SelectItem>
              </SelectContent>
            </Select>
          </div> */}
        </div>
      </div>

      {/* Runbooks Table */}
      <Card className="overflow-hidden" style={{ boxShadow: '0px 4px 6px 2px #0000001A' }}>
        {isLoading ? (
          <div className="text-center py-8">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-loading" />
            <p className="text-secondary">Loading runbooks...</p>
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-16 px-4">
            <AlertCircle className="h-12 w-12 text-danger" />
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">Error Loading Runbooks</h3>
              <p className="text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'Failed to load runbooks'}
              </p>
              <Button onClick={() => refetch()} variant="outline">
                Try Again
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50 hover:bg-muted/50 border-b">
                    {/* Checkbox column */}
                    <TableHead className="w-12 px-4">
                      <Checkbox
                        checked={selectedRunbookIds.size > 0 && selectedRunbookIds.size === paginatedRunbooks.length}
                        indeterminate={selectedRunbookIds.size > 0 && selectedRunbookIds.size < paginatedRunbooks.length}
                        onCheckedChange={toggleSelectAll}
                        aria-label="Select all runbooks"
                      />
                    </TableHead>
                    <TableHead className="table-header-text px-6">Title</TableHead>
                    <TableHead className="table-header-text px-6">Source</TableHead>
                    <TableHead className="table-header-text px-6">Last Updated</TableHead>
                    <TableHead className="table-header-text px-6">Size</TableHead>
                    <TableHead className="table-header-text px-6 text-right">
                      <span className="flex justify-end">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedRunbooks.map((runbook, index) => (
                    <TableRow
                      key={runbook.id}
                      className={cn(
                        "hover:bg-muted/50 hover:shadow-sm cursor-pointer transition-all duration-200",
                        index !== paginatedRunbooks.length - 1 && "border-b border-border/50",
                        index % 2 === 0 ? "bg-background" : "bg-muted"
                      )}
                      onClick={() => onViewRunbook(runbook)}
                    >
                      {/* Checkbox cell */}
                      <TableCell className="px-4" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={isRunbookSelected(runbook.id)}
                          onCheckedChange={() => toggleRunbookSelection(runbook.id)}
                          aria-label={`Select ${runbook.title}`}
                        />
                      </TableCell>

                      <TableCell className="px-6 py-3">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <span className="table-data-text text-foreground">
                            {runbook.title}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="px-6 py-6 table-data-text text-muted-foreground">
                        {formatSource(runbook.source)}
                      </TableCell>
                      <TableCell className="px-6 py-6 table-data-text text-muted-foreground">
                        {formatDate(runbook.lastUpdated)}
                      </TableCell>
                      <TableCell className="px-6 py-6 table-data-text text-muted-foreground">
                        {formatFileSize(runbook.size ?? 0)}
                      </TableCell>
                      <TableCell className="px-6 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-2 justify-end">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onViewRunbook(runbook)}
                            className="h-8 px-2"
                          >
                            <Eye className="h-4 w-4 mr-1 text-muted-foreground" />

                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={deletingRunbookId === runbook.id}
                                className="h-8 px-2 text-danger hover:text-danger-dark hover:bg-danger-light disabled:opacity-50"
                              >
                                {deletingRunbookId === runbook.id ? (
                                  <Loader2 className="h-4 w-4 mr-1 animate-spin text-muted-foreground" />
                                ) : (
                                  <Trash2 className="h-4 w-4 mr-1 text-muted-foreground" />
                                )}

                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Delete Runbook</AlertDialogTitle>
                                <AlertDialogDescription>
                                  Are you sure you want to delete "{runbook.title}"? This action cannot be undone.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <div className="py-4">
                                <Label htmlFor="delete-confirmation" className="text-sm font-medium">
                                  Type "delete" to confirm:
                                </Label>
                                <Input
                                  id="delete-confirmation"
                                  value={deleteConfirmationText}
                                  onChange={(e) => setDeleteConfirmationText(e.target.value)}
                                  placeholder="delete"
                                  className="mt-2 border border-gray-300 focus:border-red-500 focus:ring-red-500"
                                />
                              </div>
                              <AlertDialogFooter>
                                <AlertDialogCancel onClick={() => setDeleteConfirmationText("")}>
                                  Cancel
                                </AlertDialogCancel>
                                <AlertDialogAction
                                  className="bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                  disabled={deleteConfirmationText !== "delete" || deletingRunbookId === runbook.id}
                                  onClick={() => handleDelete(runbook)}
                                >
                                  {deletingRunbookId === runbook.id ? (
                                    <>
                                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                      Deleting...
                                    </>
                                  ) : (
                                    "Delete"
                                  )}
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {paginatedRunbooks.length === 0 && !debouncedSearchTerm && (
              <div className="text-center py-8 text-secondary">
                No runbooks available.
              </div>
            )}

            {debouncedSearchTerm && paginatedRunbooks.length === 0 && (
              <div className="text-center py-8 text-secondary">
                <div className="space-y-2">
                  <p>No runbooks match your search for "{debouncedSearchTerm}"</p>
                  {semanticSearchEnabled && (
                    <p className="text-sm">Try different keywords or disable AI search for exact matches</p>
                  )}
                </div>
              </div>
            )}

            {debouncedSearchTerm && paginatedRunbooks.length > 0 && (
              <div className="px-6 py-2 bg-surface border-t border-border text-sm text-muted-foreground">
                {semanticSearchEnabled ? (
                  <span>🧠 AI search results for "{debouncedSearchTerm}"</span>
                ) : (
                  <span>📝 Text search results for "{debouncedSearchTerm}"</span>
                )}
              </div>
            )}

            {/* Pagination */}
            {totalItems > 0 && (
              <div className="flex justify-between items-center px-6 py-4 bg-muted border-t -mt-[21px]">
                <div className="text-sm">
                  <span className="text-muted-foreground">Showing</span> <span className="font-bold">{Math.min((currentPage - 1) * pageSize + 1, totalItems)}-{Math.min(currentPage * pageSize, totalItems)}</span> of <span className="font-bold">{totalItems}</span>
                </div>

                {Math.ceil(totalItems / pageSize) > 1 && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                      disabled={currentPage === 1}
                      className="table-pg-button text-muted-foreground"
                    >
                      Previous
                    </Button>

                    <div className="flex items-center gap-2">
                      {(() => {
                        const totalPages = Math.ceil(totalItems / pageSize);
                        const pages = [];
                        const delta = 2; // Number of pages to show around current page

                        // Always show first page
                        pages.push(
                          <Button
                            key={1}
                            variant={currentPage === 1 ? "default" : "outline"}
                            onClick={() => setCurrentPage(1)}
                            className={cn(
                              "table-pg-number-btn text-muted-foreground",
                              currentPage === 1
                                ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                                : "hover:bg-muted"
                            )}
                          >
                            1
                          </Button>
                        );

                        // Show ellipsis if there's a gap after first page
                        if (currentPage > delta + 2) {
                          pages.push(
                            <span key="ellipsis-start" className="px-2 text-muted-foreground">
                              ...
                            </span>
                          );
                        }

                        // Show pages around current page
                        const startPage = Math.max(2, currentPage - delta);
                        const endPage = Math.min(totalPages - 1, currentPage + delta);

                        for (let i = startPage; i <= endPage; i++) {
                          pages.push(
                            <Button
                              key={i}
                              variant={currentPage === i ? "default" : "outline"}
                              onClick={() => setCurrentPage(i)}
                              className={cn(
                                "table-pg-number-btn text-muted-foreground",
                                currentPage === i
                                  ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                                  : "hover:bg-muted"
                              )}
                            >
                              {i}
                            </Button>
                          );
                        }

                        // Show ellipsis if there's a gap before last page
                        if (currentPage < totalPages - delta - 1) {
                          pages.push(
                            <span key="ellipsis-end" className="px-2 text-muted-foreground">
                              ...
                            </span>
                          );
                        }

                        // Always show last page if more than 1 page
                        if (totalPages > 1) {
                          pages.push(
                            <Button
                              key={totalPages}
                              variant={currentPage === totalPages ? "default" : "outline"}
                              onClick={() => setCurrentPage(totalPages)}
                              className={cn(
                                "table-pg-number-btn text-muted-foreground",
                                currentPage === totalPages
                                  ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                                  : "hover:bg-muted"
                              )}
                            >
                              {totalPages}
                            </Button>
                          );
                        }

                        return pages;
                      })()}
                    </div>

                    <Button
                      variant="outline"
                      onClick={() => setCurrentPage(Math.min(Math.ceil(totalItems / pageSize), currentPage + 1))}
                      disabled={currentPage === Math.ceil(totalItems / pageSize)}
                      className="table-pg-button bg-card text-muted-foreground"
                    >
                      Next
                    </Button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}