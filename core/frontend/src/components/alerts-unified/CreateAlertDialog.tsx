import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Checkbox } from "../ui/checkbox";
import { Loader2 } from "lucide-react";
import { KeyValueInput } from "./KeyValueInput";
import { toast } from "sonner";
import { useCreateAlert } from "../../hooks/useCreateAlert";

interface CreateAlertDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateAlertDialog({ open, onOpenChange }: CreateAlertDialogProps) {
  // Use the custom hook for alert creation
  const createAlertMutation = useCreateAlert();

  // Toggle for JSON mode
  const [useJsonMode, setUseJsonMode] = useState(false);

  // Form state
  const [alertName, setAlertName] = useState("");
  const [severity, setSeverity] = useState<"P1" | "P2" | "P3">("P3");
  const [alertStatus, setAlertStatus] = useState<"firing" | "resolved">("firing");
  const [description, setDescription] = useState("");
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [annotations, setAnnotations] = useState<Record<string, string>>({});
  const [triggerTriage, setTriggerTriage] = useState(true); // Default enabled

  // JSON mode state
  const [jsonInput, setJsonInput] = useState("");
  const [jsonError, setJsonError] = useState("");

  const isValid = useJsonMode
    ? jsonInput.trim() !== ""
    : (alertName.trim() !== "" && description.trim() !== "");

  const isSubmitting = createAlertMutation.isPending;

  const parseJsonAlert = () => {
    setJsonError("");

    try {
      const parsed = JSON.parse(jsonInput);

      // Validate required fields
      const errors: string[] = [];

      // 1. Validate alert_name
      const alertName = parsed.alert_name || parsed.labels?.alertname;
      if (!alertName) {
        errors.push("ERROR: Missing 'alert_name' or 'labels.alertname'");
      } else if (typeof alertName !== 'string' || alertName.trim() === '') {
        errors.push("ERROR: 'alert_name' must be a non-empty string");
      }

      // 2. Validate severity
      if (!parsed.severity) {
        errors.push("ERROR: Missing 'severity' (required: P1, P2, or P3)");
      } else if (!["P1", "P2", "P3"].includes(parsed.severity)) {
        errors.push(`ERROR: Invalid 'severity': "${parsed.severity}" (must be P1, P2, or P3)`);
      }

      // 3. Validate description
      const description = parsed.description || parsed.annotations?.description;
      if (!description) {
        errors.push("ERROR: Missing 'description' or 'annotations.description'");
      } else if (typeof description !== 'string' || description.trim() === '') {
        errors.push("ERROR: 'description' must be a non-empty string");
      }

      // 4. Validate alert_status (optional, but if provided must be valid)
      if (parsed.alert_status && !["firing", "resolved"].includes(parsed.alert_status)) {
        errors.push(`ERROR: Invalid 'alert_status': "${parsed.alert_status}" (must be "firing" or "resolved")`);
      }

      // 5. Validate status (alternative field name)
      if (parsed.status && !["firing", "resolved"].includes(parsed.status)) {
        errors.push(`ERROR: Invalid 'status': "${parsed.status}" (must be "firing" or "resolved")`);
      }

      // 6. Validate labels (optional, but if provided must be object)
      if (parsed.labels && typeof parsed.labels !== 'object') {
        errors.push("ERROR: 'labels' must be an object (key-value pairs)");
      }

      // 7. Validate annotations (optional, but if provided must be object)
      if (parsed.annotations && typeof parsed.annotations !== 'object') {
        errors.push("ERROR: 'annotations' must be an object (key-value pairs)");
      }

      // 8. Validate trigger_triage (optional, but if provided must be boolean)
      if (parsed.trigger_triage !== undefined && typeof parsed.trigger_triage !== 'boolean') {
        errors.push("ERROR: 'trigger_triage' must be true or false");
      }

      // Return errors if any
      if (errors.length > 0) {
        setJsonError(errors.join("\n"));
        return null;
      }

      // Extract and clean values
      const cleanedLabels = parsed.labels || {};
      const cleanedAnnotations = parsed.annotations || {};

      // Ensure labels and annotations are objects with string keys/values only
      const validateKeyValuePairs = (obj: any, fieldName: string): Record<string, string> => {
        const result: Record<string, string> = {};
        for (const [key, value] of Object.entries(obj)) {
          if (typeof key === 'string' && (typeof value === 'string' || typeof value === 'number')) {
            result[key] = String(value);
          } else {
            errors.push(`ERROR: ${fieldName}.${key} must have a string or number value`);
          }
        }
        return result;
      };

      const validatedLabels = validateKeyValuePairs(cleanedLabels, "labels");
      const validatedAnnotations = validateKeyValuePairs(cleanedAnnotations, "annotations");

      if (errors.length > 0) {
        setJsonError(errors.join("\n"));
        return null;
      }

      // Return validated payload
      return {
        alert_name: String(alertName).trim(),
        severity: parsed.severity,
        alert_status: parsed.alert_status || parsed.status || "firing",
        description: String(description).trim(),
        labels: validatedLabels,
        annotations: validatedAnnotations,
        trigger_triage: parsed.trigger_triage !== undefined ? Boolean(parsed.trigger_triage) : true,
      };
    } catch (error: any) {
      // Preserve SyntaxError details (line/column numbers)
      let errorDetails = error.message;
      if (error instanceof SyntaxError && error.message) {
        // Extract position information if available
        const positionMatch = error.message.match(/position (\d+)/);
        if (positionMatch) {
          const position = parseInt(positionMatch[1]);
          const lines = jsonInput.substring(0, position).split('\n');
          const lineNum = lines.length;
          const colNum = lines[lines.length - 1].length + 1;
          errorDetails = `${error.message}\nAt line ${lineNum}, column ${colNum}`;
        }
      }
      setJsonError(`ERROR: Invalid JSON format: ${errorDetails}\n\nPlease ensure your JSON is properly formatted with valid syntax.`);
      return null;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isValid) return;

    let payload;

    if (useJsonMode) {
      // Parse and validate JSON
      payload = parseJsonAlert();
      if (!payload) {
        // Show validation errors as toast
        if (jsonError) {
          const errors = jsonError.split('\n');
          toast.error(errors[0], {
            description: errors.slice(1).join('\n'),
            duration: 5000,
          });
        }
        return; // Validation failed, error already set
      }
    } else {
      // Use form values
      payload = {
        alert_name: alertName.trim(),
        severity,
        alert_status: alertStatus,
        description: description.trim(),
        labels,
        annotations,
        trigger_triage: triggerTriage,
      };
    }

    // Use the mutation hook to create the alert
    createAlertMutation.mutate(payload, {
      onSuccess: () => {
        // Close dialog
        onOpenChange(false);

        // Reset form
        resetForm();
      },
    });
  };

  const resetForm = () => {
    setAlertName("");
    setSeverity("P3");
    setAlertStatus("firing");
    setDescription("");
    setLabels({});
    setAnnotations({});
    setTriggerTriage(true);
    setJsonInput("");
    setJsonError("");
    setUseJsonMode(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[800px] !h-[90vh] !max-h-[90vh] flex flex-col !p-0 gap-0">
        <DialogHeader className="flex-shrink-0 px-6 pt-6 pb-4">
          <DialogTitle className="text-xl font-semibold">Create New Alert</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground mt-2">
            Manually create an alert for testing, training, or when monitoring tools are down.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto px-6 py-2 space-y-4">
            {/* JSON Mode Toggle */}
            <div className="flex items-center space-x-2 p-3 bg-muted/50 rounded-md flex-shrink-0">
              <Checkbox
                id="jsonMode"
                checked={useJsonMode}
                onCheckedChange={(checked) => {
                  setUseJsonMode(checked as boolean);
                  setJsonError("");
                }}
                disabled={isSubmitting}
              />
              <Label htmlFor="jsonMode" className="text-sm font-medium cursor-pointer">
                Use JSON format (paste alert JSON payload instead of filling form)
              </Label>
            </div>

            {!useJsonMode ? (
              // Form Mode
              <>
          {/* Alert Name */}
          <div className="space-y-2">
            <Label htmlFor="alertName" className="text-sm font-semibold">
              Alert Name <span className="text-red-500">*</span>
            </Label>
            <Input
              id="alertName"
              placeholder="e.g., High CPU Usage on Production Server"
              value={alertName}
              onChange={(e) => setAlertName(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          {/* Severity and Status */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="severity" className="text-sm font-semibold">
                Severity <span className="text-red-500">*</span>
              </Label>
              <Select value={severity} onValueChange={(value: "P1" | "P2" | "P3") => setSeverity(value)} disabled={isSubmitting}>
                <SelectTrigger id="severity">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="P1">P1 - Critical</SelectItem>
                  <SelectItem value="P2">P2 - High</SelectItem>
                  <SelectItem value="P3">P3 - Medium</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="alertStatus" className="text-sm font-semibold">
                Alert Status <span className="text-red-500">*</span>
              </Label>
              <Select value={alertStatus} onValueChange={(value: "firing" | "resolved") => setAlertStatus(value)} disabled={isSubmitting}>
                <SelectTrigger id="alertStatus">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="firing">Firing</SelectItem>
                  <SelectItem value="resolved">Resolved</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="description" className="text-sm font-semibold">
              Description <span className="text-red-500">*</span>
            </Label>
            <Textarea
              id="description"
              placeholder="Detailed description of the issue..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              required
              className="min-h-[100px]"
            />
          </div>

          {/* Labels */}
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Labels (Optional)</Label>
            <KeyValueInput
              value={labels}
              onChange={setLabels}
              placeholder={{ key: "environment", value: "production" }}
              disabled={isSubmitting}
            />
          </div>

          {/* Annotations */}
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Annotations (Optional)</Label>
            <KeyValueInput
              value={annotations}
              onChange={setAnnotations}
              placeholder={{ key: "runbook", value: "https://..." }}
              disabled={isSubmitting}
            />
          </div>

          {/* Trigger Triage */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="triggerTriage"
              checked={triggerTriage}
              onCheckedChange={(checked) => setTriggerTriage(checked as boolean)}
              disabled={isSubmitting}
            />
            <Label htmlFor="triggerTriage" className="text-sm cursor-pointer">
              Trigger AI triage immediately upon creation (recommended)
            </Label>
          </div>
          </>
          ) : (
            // JSON Mode
            <>
              {/* JSON Input */}
              <div className="space-y-2 flex-shrink-0">
                <div className="flex items-center justify-between">
                  <Label htmlFor="jsonInput" className="text-sm font-semibold">
                    Alert JSON Payload <span className="text-red-500">*</span>
                  </Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const result = parseJsonAlert();
                      if (result) {
                        toast.success("JSON is valid! All required fields present.");
                      } else if (jsonError) {
                        // Show validation errors as toast
                        const errors = jsonError.split('\n').filter(e => e.trim());
                        toast.error(errors[0], {
                          description: errors.slice(1).join('\n'),
                          duration: 6000,
                        });
                      }
                    }}
                    disabled={isSubmitting || !jsonInput.trim()}
                  >
                    Validate JSON
                  </Button>
                </div>
                <div className="h-[350px] flex-shrink-0">
                  <Textarea
                    id="jsonInput"
                    placeholder=""
                    value={jsonInput}
                    onChange={(e) => {
                      setJsonInput(e.target.value);
                      setJsonError("");
                    }}
                    disabled={isSubmitting}
                    className={`h-full w-full font-mono text-sm resize-none overflow-y-auto !field-sizing-[initial] ${jsonError ? 'border-red-500' : ''}`}
                    style={{ fieldSizing: 'initial' }}
                  />
                </div>
              </div>

              {/* Required Fields Info */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3 flex-shrink-0">
                <p className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-1">Required Fields:</p>
                <ul className="text-xs text-blue-800 dark:text-blue-200 space-y-1 list-disc list-inside">
                  <li><code>alert_name</code> or <code>labels.alertname</code></li>
                  <li><code>severity</code>: "P1", "P2", or "P3"</li>
                  <li><code>description</code> or <code>annotations.description</code></li>
                </ul>
              </div>

              {/* Trigger Triage - JSON Mode */}
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="triggerTriageJson"
                  checked={triggerTriage}
                  onCheckedChange={(checked) => setTriggerTriage(checked as boolean)}
                  disabled={isSubmitting}
                />
                <Label htmlFor="triggerTriageJson" className="text-sm cursor-pointer">
                  Trigger AI triage immediately upon creation (recommended)
                </Label>
              </div>
            </>
          )}
          </div>

          {/* Actions - Fixed at bottom */}
          <div className="flex justify-end gap-3 pt-4 px-6 pb-6 flex-shrink-0 bg-background">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                resetForm();
              }}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!isValid || isSubmitting}
            >
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isSubmitting ? "Creating..." : "Create Alert"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
