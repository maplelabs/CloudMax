import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { X, Search } from "lucide-react";
import { cn } from "./ui/utils";

export interface FilterOption {
  id: string;
  label: string;
  category: string;
}

interface FilterBarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  activeFilters: FilterOption[];
  onRemoveFilter: (filterId: string) => void;
  onClearAll: () => void;
  children?: React.ReactNode;
  className?: string;
}

export function FilterBar({
  searchValue,
  onSearchChange,
  searchPlaceholder = "Search...",
  activeFilters,
  onRemoveFilter,
  onClearAll,
  children,
  className
}: FilterBarProps) {
  const hasActiveFilters = activeFilters.length > 0 || searchValue.length > 0;

  return (
    <div className={cn("space-y-4", className)}>
      {/* Search and Filter Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Search Input */}
        <div className="relative min-w-64">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted" />
          <Input
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-10"
          />
        </div>
        
        {/* Additional Filter Controls */}
        {children}
        
        {/* Clear All */}
        {hasActiveFilters && (
          <Button 
            variant="outline" 
            size="sm" 
            onClick={onClearAll}
            className="text-secondary"
          >
            Reset All
          </Button>
        )}
      </div>
      
      {/* Active Filters */}
      {activeFilters.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-secondary font-medium">Filters:</span>
          {activeFilters.map((filter) => (
            <Badge
              key={filter.id}
              variant="secondary"
              className="gap-1 bg-success-light text-success-dark border-success hover:bg-success-light"
            >
              <span className="text-xs text-success">{filter.category}:</span>
              {filter.label}
              <button
                onClick={() => onRemoveFilter(filter.id)}
                className="ml-1 hover:bg-success-dark rounded-full p-0.5"
                aria-label={`Remove ${filter.label} filter`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}