import { useState } from "react";
import { useRunbook, useUpdateRunbook } from "../../hooks/useRunbooks";
import { Button } from "../ui/button";
import { ScrollArea } from "../ui/scroll-area";
import { Input } from "../ui/input";
import { Calendar, Loader2, Edit3, Save, X, ChevronLeftIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Editor from "@monaco-editor/react";

interface RunbookViewProps {
  runbook: {
    id: string;
    title: string;
    lastUpdated: string;
    size: string;
    content: string;
  };
  onBack: () => void;
}

export function RunbookView({ runbook, onBack }: RunbookViewProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");

  const {
    data: runbookResponse,
    isLoading,
    isError,
    error,
    refetch
  } = useRunbook(runbook.id);

  const updateMutation = useUpdateRunbook();

  const handleEdit = () => {
    setIsEditing(true);
    setEditTitle(runbookResponse?.name || runbook.title);
    setEditContent(runbookResponse?.content || "");
  };

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({
        id: runbook.id,
        updateData: {
          title: editTitle,
          content: editContent
        }
      });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to update runbook:', error);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditTitle("");
    setEditContent("");
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-none border-border-light  px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={onBack}
              className="gap-2 text-slate-600 hover:text-slate-900 self-start"
            >
              <ChevronLeftIcon className="h-4 w-4" />
              Back to Runbooks
            </Button>

            <div className="">
              {isEditing ? (
                <div className="flex items-center gap-2">
                  <Input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="headline text-slate-900 border focus border-slate-800 rounded px-2 py-1 h-auto font-semibold text bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 flex-1"
                    placeholder="Runbook title"
                  />
                  <Edit3 className="h-4 w-4 text-muted" />
                </div>
              ) : (
                <h1 className="page-title text-bold title-lg-header px-4">{runbookResponse?.name || runbook.title}</h1>
              )}
              <div className="flex items-center gap-4 text-secondary body-s mt-1 px-4">
                 {runbookResponse && (<span>{runbookResponse.size}</span>) }
                <div className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  <span>
                    {new Date(runbook.lastUpdated).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit"
                    })}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <Button
                  onClick={handleSave}
                  disabled={updateMutation.isPending}
                  size="sm"
                  className="gap-2 active-range-bg"
                >
                  {updateMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save
                </Button>
                <Button
                  onClick={handleCancel}
                  variant="outline"
                  size="sm"
                  className="gap-2"
                >
                  <X className="h-4 w-4" />
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                onClick={handleEdit}
                variant="outline"
                size="sm"
                className="gap-2"
              >
                <Edit3 className="h-4 w-4" />
                Edit
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Full-width Content */}
      <div className="flex-1 overflow-hidden px-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin text-loading mr-3" />
            <span className="text-secondary">Fetching runbook...</span>
          </div>
        )
          : isError ? (
            <div className="flex flex-col items-center justify-center h-full p-4 text-center">
              <span className="text-danger mb-2">Error loading runbook: {(error as Error).message}</span>
              <Button onClick={() => refetch()}>Retry</Button>
            </div>
          )
            : isEditing ? (
              <div className="flex-1 flex flex-col px-8 py-6 min-h-0">
                <div className="flex-1 border border-slate-200 rounded-lg overflow-hidden min-h-0">
                  <Editor
                    height="500px"
                    defaultLanguage="markdown"
                    value={editContent}
                    onChange={(value) => setEditContent(value || "")}
                    options={{
                      minimap: { enabled: false },
                      wordWrap: "on",
                      lineNumbers: "on",
                      fontSize: 14,
                      fontFamily: "JetBrains Mono, Consolas, Monaco, monospace",
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      theme: "vs-light",
                      padding: { top: 16, bottom: 16 }
                    }}
                  />
                </div>
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="px-8 py-6 box-shadow bg-card" style={{margin:8}}>
                  <div className="prose prose-lg max-w-none runbook-content">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({ children }) => <h1 className="text-2xl font-semibold text-foreground mt-8 mb-4 first:mt-0">{children}</h1>,
                        h2: ({ children }) => <h2 className="text-xl font-semibold text-foreground mt-6 mb-3">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-lg font-medium text-foreground mt-5 mb-2">{children}</h3>,
                        p: ({ children }) => <p className="text-secondary mb-4 leading-relaxed">{children}</p>,
                        ul: ({ children }) => <ul className="list-disc pl-6 mb-4 space-y-1">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal pl-6 mb-4 space-y-1">{children}</ol>,
                        li: ({ children }) => <li className="text-secondary">{children}</li>,
                        code: ({ node, children }) =>
                          (node && (node as any).inline) ? (
                            <code className="bg-surface-secondary text-foreground px-1.5 py-0.5 rounded text-sm font-mono">{children}</code>
                          ) : (
                            <code className="block bg-surface text-foreground p-4 rounded-lg border border-light text-sm font-mono whitespace-pre-wrap overflow-x-auto">{children}</code>
                          ),
                        pre: ({ children }) => <div className="mb-6">{children}</div>,
                        blockquote: ({ children }) => <blockquote className="border-l-4 border-info-light pl-4 italic text-secondary mb-4">{children}</blockquote>,
                        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                        em: ({ children }) => <em className="italic text-secondary">{children}</em>,
                        table: ({ children }) => (
                          <div className="my-6 w-full overflow-x-auto">
                            <table className="w-full border-collapse border border-slate-300">{children}</table>
                          </div>
                        ),
                        thead: ({ children }) => <thead className="bg-slate-100">{children}</thead>,
                        tbody: ({ children }) => <tbody>{children}</tbody>,
                        tr: ({ children }) => <tr className="border-b border-slate-300">{children}</tr>,
                        th: ({ children }) => <th className="border border-slate-300 px-4 py-2 text-left font-semibold text-foreground">{children}</th>,
                        td: ({ children }) => <td className="border border-slate-300 px-4 py-2 text-secondary">{children}</td>,
                      }}
                    >
                      {runbookResponse.content}
                    </ReactMarkdown>
                  </div>
                </div>
              </ScrollArea>
            )}

      </div>
    </div>
  );
}