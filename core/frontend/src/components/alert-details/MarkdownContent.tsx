import ReactMarkdown from "react-markdown";

interface MarkdownContentProps {
  content?: string;
}

export const MarkdownContent = ({ content }: MarkdownContentProps) => {
  if (!content) {
    return <div className="text-secondary text-center py-4">No content available</div>;
  }

  return (
    <div className="prose prose-slate max-w-none">
      <ReactMarkdown
        components={{
          // Custom styling for different elements
          h1: ({ children }) => (
            <h1 className="text-2xl font-semibold mt-8 mb-6 text-foreground">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold mt-6 mb-3 text-foreground">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-medium mt-4 mb-2 text-foreground">{children}</h3>
          ),
          p: ({ children }) => (
            <p className="mb-3 text-secondary leading-relaxed">{children}</p>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),
          code: ({ children }) => (
            <code className="px-1 py-0.5 bg-surface-secondary rounded text-sm font-mono text-foreground">
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="my-4 p-4 bg-surface-secondary rounded text-sm font-mono overflow-x-auto">
              {children}
            </pre>
          ),
          ul: ({ children }) => (
            <ul className="mb-4 text-secondary list-disc list-inside space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-4 text-secondary list-decimal list-inside space-y-1">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="text-secondary">{children}</li>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
