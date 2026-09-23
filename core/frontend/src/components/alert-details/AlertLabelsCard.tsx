import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { TagIcon } from "lucide-react";

interface AlertLabelsCardProps {
  labels: Record<string, unknown>;
}

const formatLabelKey = (key: string): string => {
  return key
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

export function AlertLabelsCard({ labels }: AlertLabelsCardProps) {
  if (!labels || Object.keys(labels).length === 0) {
    return null;
  }

  return (
    <Card className="box-shadow rounded-lg mr-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 info-title-text">
          <TagIcon size={12} />
          Labels
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {Object.entries(labels).map(([key, value]) => (
            <div key={key}>
              <label className="text-sm font-medium text-tertiary">{formatLabelKey(key)}</label>
              <p className="text-foreground mt-1 break-all">{value as string}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
