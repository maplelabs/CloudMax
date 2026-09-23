import { useState, useEffect } from "react";
import { cn } from "./ui/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from "./ui/dropdown-menu";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Calendar } from "./ui/calendar";
import { ChevronDown } from "lucide-react";

export type TimeRange = "30m" | "1h" | "24h" | "7d" | "30d" | "custom";

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange, customRange?: { start: Date; end: Date }) => void;
  customRange?: { start: Date; end: Date };
  className?: string;
}

const presetLabels = {
  "30m": "30 minutes",
  "1h": "1 hour",
  "24h": "1 day",
  "7d": "1 week",
  "30d": "1 month",
  "custom": "Custom",
};

export function TimeRangeSelector({
  value,
  onChange,
  customRange,
  className,
}: TimeRangeSelectorProps) {
  // Helper function to get default dates
  const getDefaultDates = () => {
    const end = new Date(); // Today
    end.setHours(0, 0, 0, 0);
    const start = new Date();
    start.setDate(start.getDate() - 1); // Yesterday
    start.setHours(0, 0, 0, 0);
    return { start, end };
  };

  const defaultDates = customRange || getDefaultDates();

  const [open, setOpen] = useState(false);
  const [startDate, setStartDate] = useState<Date | undefined>(defaultDates.start);
  const [endDate, setEndDate] = useState<Date | undefined>(defaultDates.end);
  const [activeField, setActiveField] = useState<"start" | "end">("start");
  const [calendarMonth, setCalendarMonth] = useState<Date>(new Date());
  const [dateRangeError, setDateRangeError] = useState<string>("");

  // Sync with customRange prop changes
  useEffect(() => {
    if (customRange?.start && customRange?.end) {
      setStartDate(customRange.start);
      setEndDate(customRange.end);
    } else {
      // Set defaults if no custom range provided
      const defaults = getDefaultDates();
      setStartDate(defaults.start);
      setEndDate(defaults.end);
    }
  }, [customRange]);

  const formatDateLabel = (date: Date) => {
    const d = `${date.getDate()}`.padStart(2, "0");
    const m = `${date.getMonth() + 1}`.padStart(2, "0");
    const y = date.getFullYear();
    return `${d}-${m}-${y}`;
  };

  const formatDate = (date?: Date) => {
    if (!date || !(date instanceof Date) || isNaN(date.getTime())) return "";
    try {
      const day = String(date.getDate()).padStart(2, '0');
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const year = date.getFullYear();
      return `${day}-${month}-${year}`;
    } catch {
      return "";
    }
  };

  const getDisplayLabel = () => {
    if (value === "custom") {
      if (customRange?.start && customRange?.end) {
        return `${formatDateLabel(customRange.start)} to ${formatDateLabel(customRange.end)}`;
      }
      return "Custom";
    }
    return presetLabels[value] ?? "Select Time Range";
  };

  const handlePresetSelect = (range: TimeRange) => {
    if (range !== "custom") {
      onChange(range);
      setOpen(false);
    }
  };

  const validateDateRange = (start: Date, end: Date): string => {
    const diffTime = Math.abs(end.getTime() - start.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    if (diffDays > 90) {
      return "Date range cannot exceed 90 days";
    }
    return "";
  };

  const handleDateSelect = (date: Date | undefined) => {
    if (!date || !(date instanceof Date) || isNaN(date.getTime())) return;

    if (activeField === "start") {
      setStartDate(date);
      setCalendarMonth(date);

      if (endDate) {
        const error = validateDateRange(date, endDate);
        setDateRangeError(error);

        if (endDate < date) {
          setEndDate(undefined);
          setDateRangeError("");
        }
      } else {
        setDateRangeError("");
      }

      setActiveField("end");
    } else {
      if (startDate && date < startDate) return;

      if (startDate) {
        const error = validateDateRange(startDate, date);
        setDateRangeError(error);

        if (!error) {
          setEndDate(date);
          setCalendarMonth(date);
        }
      } else {
        setEndDate(date);
        setCalendarMonth(date);
      }
    }
  };

  const handleApply = () => {
    if (!startDate || !endDate) return;
    if (!(startDate instanceof Date) || isNaN(startDate.getTime())) return;
    if (!(endDate instanceof Date) || isNaN(endDate.getTime())) return;
    if (startDate > endDate) return;

    const error = validateDateRange(startDate, endDate);
    if (error) {
      setDateRangeError(error);
      return;
    }

    const normalizedStart = new Date(startDate);
    normalizedStart.setHours(0, 0, 0, 0);

    const normalizedEnd = new Date(endDate);
    normalizedEnd.setHours(23, 59, 59, 999);

    onChange("custom", { start: normalizedStart, end: normalizedEnd });
    setOpen(false);
  };

  const handleClear = () => {
    const defaults = getDefaultDates();
    setStartDate(defaults.start);
    setEndDate(defaults.end);
    setDateRangeError("");
    setCalendarMonth(new Date());
    setActiveField("start");
  };

  const today = new Date();
  today.setHours(23, 59, 59, 999);

  const hasCompleteRange = !!startDate && !!endDate && startDate <= endDate && !dateRangeError;

  return (
    <div className="relative">
      <Label className="absolute left-3 bg-white px-1 text-xs text-muted-foreground z-10 bg-muted rounded-md" style={{marginTop:-8}}>
        Select Time Range
      </Label>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className={cn("border border-border-medium justify-between", className)}
            style={{height:38, minWidth:180}}
          >
            <span className="truncate text-sm text-muted-foreground">
              {getDisplayLabel()}
            </span>
            <ChevronDown className="ml-2 h-4 w-4 opacity-50" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {(Object.keys(presetLabels) as Array<keyof typeof presetLabels>)
            .filter(range => range !== "custom")
            .map((range) => (
              <DropdownMenuItem
                key={range}
                onClick={() => handlePresetSelect(range as TimeRange)}
              >
                {presetLabels[range]}
              </DropdownMenuItem>
            ))}

          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              Custom
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="w-[320px] p-4 overflow-visible max-h-[600px]">
              <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
                <div className="text-sm font-semibold mb-2">Select Custom Date Range</div>
                <div className="flex gap-3">
                  <div className="flex-1 space-y-1">
                    <Label htmlFor="custom-start-date" className="text-xs text-muted-foreground">
                      Start Date
                    </Label>
                    <Input
                      id="custom-start-date"
                      type="text"
                      readOnly
                      value={formatDate(startDate)}
                      placeholder="Select"
                      className={cn(
                        "h-9 text-xs",
                        activeField === "start" && "border-primary ring-primary/40",
                      )}
                      onFocus={() => {
                        setActiveField("start");
                        if (startDate) {
                          setCalendarMonth(startDate);
                        }
                      }}
                    />
                  </div>
                  <div className="flex-1 space-y-1">
                    <Label htmlFor="custom-end-date" className="text-xs text-muted-foreground">
                      End Date
                    </Label>
                    <Input
                      id="custom-end-date"
                      type="text"
                      readOnly
                      value={formatDate(endDate)}
                      placeholder="Select"
                      className={cn(
                        "h-9 text-xs",
                        activeField === "end" && "border-primary ring-primary/40",
                        !startDate && "opacity-50 cursor-not-allowed",
                      )}
                      onFocus={() => {
                        if (startDate) {
                          setActiveField("end");
                          if (endDate) {
                            setCalendarMonth(endDate);
                          }
                        }
                      }}
                      disabled={!startDate}
                    />
                  </div>
                </div>

                <Calendar
                  mode="single"
                  selected={activeField === "start" ? startDate : endDate}
                  onSelect={handleDateSelect}
                  showOutsideDays={false}
                  disabled={(date) => {
                    if (date > today) return true;
                    if (activeField === "end" && startDate) {
                      return date < startDate;
                    }
                    return false;
                  }}
                  numberOfMonths={1}
                  className={cn("border rounded-md")}
                  month={calendarMonth}
                  onMonthChange={setCalendarMonth}
                  captionLayout="dropdown-buttons"
                  fromYear={2020}
                  toYear={today.getFullYear()}
                  classNames={{
                    caption_label: "hidden",
                    caption: "flex justify-center pt-1 relative items-center",
                    caption_dropdowns: "flex gap-2",
                    dropdown_month: "flex-1",
                    dropdown_year: "flex-1",
                    vhidden: "hidden"
                  }}
                />

                {dateRangeError && (
                  <p className="ml-2 text-xs text-danger" role="alert">
                    {dateRangeError}
                  </p>
                )}

                <div className="flex justify-between gap-2 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleClear}
                  >
                    Reset
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="active-range-bg"
                    onClick={handleApply}
                    disabled={!hasCompleteRange}
                  >
                    Apply
                  </Button>
                </div>
              </div>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
