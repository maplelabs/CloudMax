import { Card, CardContent } from "../ui/card";
import { AlertCircle } from "lucide-react";
import { RootCauseContent } from "../alert-details/RootCauseContent";

interface GroupRootCauseTabProps {
  rootCause?: {
    content: string;
  } | null;
}

export function GroupRootCauseTab({ rootCause }: GroupRootCauseTabProps) {
  if (!rootCause) {
    return (
      <Card className="box-shadow rounded-lg mr-2">
        <CardContent className="px-6">
          <div className="flex flex-col items-center justify-center py-12">
            <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No Root Cause Analysis Available</h3>
            <p className="text-sm text-muted-foreground">
              Please run triage on this alert group first
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="pb-6">
      <Card className="box-shadow rounded-lg mr-2">
        <CardContent className="px-6">
          <RootCauseContent content={rootCause.content} />
        </CardContent>
      </Card>
    </div>
  );
}
