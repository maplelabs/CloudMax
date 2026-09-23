import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { LucideIcon, ExternalLink } from "lucide-react";

interface KeyValueCardProps {
  title: string;
  icon: LucideIcon;
  data: Record<string, string>;
}

/**
 * Reusable card component for displaying key-value pairs (labels, annotations, etc.)
 */
export function KeyValueCard({ title, icon: Icon, data }: KeyValueCardProps) {
  if (!data || Object.keys(data).length === 0) {
    return null;
  }

  // Fields that should be displayed in full width (typically long text)
  const fullWidthFields = ['description', 'summary'];

  // Separate full-width fields from regular fields
  const fullWidthEntries = Object.entries(data).filter(([key]) =>
    fullWidthFields.includes(key.toLowerCase())
  );
  const regularEntries = Object.entries(data).filter(([key]) =>
    !fullWidthFields.includes(key.toLowerCase())
  );

  // Helper to detect if value is a URL
  const isURL = (str: string) => {
    try {
      return /^https?:\/\//i.test(str);
    } catch {
      return false;
    }
  };

  // Helper to render value with proper formatting
  const renderValue = (value: string) => {
    if (isURL(value)) {
      return (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="text-info hover:underline flex items-center gap-1 break-words overflow-wrap-anywhere"
        >
          <span className="break-words">{value}</span>
          <ExternalLink className="h-3 w-3 flex-shrink-0" />
        </a>
      );
    }
    return <p className="text-foreground mt-1 break-words whitespace-pre-wrap">{value}</p>;
  };

  return (
    <Card className="box-shadow rounded-lg mr-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 info-title-text">
          <Icon size={12} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Regular fields in 2-column grid */}
          {regularEntries.length > 0 && (
            <div className="grid grid-cols-2 gap-4">
              {regularEntries.map(([key, value]) => (
                <div key={key}>
                  <label className="text-sm font-medium text-tertiary">{key}</label>
                  {renderValue(value)}
                </div>
              ))}
            </div>
          )}

          {/* Full-width fields */}
          {fullWidthEntries.map(([key, value]) => (
            <div key={key} className="w-full">
              <label className="text-sm font-medium text-tertiary">{key}</label>
              <div className="mt-1 text-sm text-foreground break-words whitespace-pre-wrap overflow-wrap-anywhere">
                {value}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
