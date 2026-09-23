import { Input } from "../ui/input";
import { Search, Brain, CheckCircle } from "lucide-react";
import { cn } from "../ui/utils";

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  semanticSearchEnabled: boolean;
  onSemanticSearchToggle: () => void;
  placeholder?: string;
}

export function SearchInput({
  value,
  onChange,
  semanticSearchEnabled,
  onSemanticSearchToggle,
  placeholder = "Search runbooks..."
}: SearchInputProps) {
  return (
    <div >
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
        <Input
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="pl-10 pr-10 bg-white"
        />
        <button
          onClick={onSemanticSearchToggle}
          className={cn(
            "absolute right-3 top-1/2 transform -translate-y-1/2 h-4 w-4 transition-colors",
            semanticSearchEnabled ? "text-green-600" : "text-slate-400 hover:text-slate-600"
          )}
          title={semanticSearchEnabled ? "Disable AI search" : "Enable AI search"}
        >
          <Brain className="h-4 w-4" />
        </button>
      </div>
      {semanticSearchEnabled && (
        <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <span>AI-powered semantic search enabled</span>
        </div>
      )}
    </div>
  );
}