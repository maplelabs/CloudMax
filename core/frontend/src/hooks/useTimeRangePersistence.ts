import { useState, useEffect } from "react";
import { TimeRange } from "../components/time-range-selector";

const TIME_RANGE_STORAGE_KEY = "app-time-range";
const CUSTOM_TIME_RANGE_STORAGE_KEY = "app-custom-time-range";

export function useTimeRangePersistence() {
  // Initialize state from localStorage or use default
  const [timeRange, setTimeRange] = useState<TimeRange>(() => {
    const stored = localStorage.getItem(TIME_RANGE_STORAGE_KEY);
    return (stored as TimeRange) || "1h";
  });

  const [customTimeRange, setCustomTimeRange] = useState<{ start: Date; end: Date } | undefined>(() => {
    const stored = localStorage.getItem(CUSTOM_TIME_RANGE_STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        return {
          start: new Date(parsed.start),
          end: new Date(parsed.end)
        };
      } catch {
        return undefined;
      }
    }
    return undefined;
  });

  // Persist to localStorage whenever timeRange changes
  useEffect(() => {
    localStorage.setItem(TIME_RANGE_STORAGE_KEY, timeRange);
  }, [timeRange]);

  // Persist custom time range to localStorage
  useEffect(() => {
    if (customTimeRange) {
      localStorage.setItem(CUSTOM_TIME_RANGE_STORAGE_KEY, JSON.stringify(customTimeRange));
    } else {
      localStorage.removeItem(CUSTOM_TIME_RANGE_STORAGE_KEY);
    }
  }, [customTimeRange]);

  const handleTimeRangeChange = (range: TimeRange, customRange?: { start: Date; end: Date }) => {
    setTimeRange(range);
    setCustomTimeRange(customRange);
  };

  return {
    timeRange,
    customTimeRange,
    handleTimeRangeChange
  };
}
