import { useQuery } from '@tanstack/react-query';
import apiClient from '../service/api';
import { TimeRange } from '../components/time-range-selector';

interface KpiMetric {
  label: string;
  value: string;
  delta: {
    value: number;
    isPositive: boolean;
    period: string;
  } | null;
  tooltip: string;
}

interface PlotDataPoint {
  timestamp: number;
  value: number;
}

interface PlotDetails {
  plot_type: "pie" | "line";
  data?: any[];
  data_points?: PlotDataPoint[];
  color?: string;
  show_dots?: boolean;
  average?: number;
}

interface Plot {
  title: string;
  plot_details: PlotDetails;
  tooltip: string;
}

interface ApiResponse {
  kpi_metrics: KpiMetric[];
  plots: Plot[];
}

interface StatsQueryParams {
  timeRange: TimeRange;
  customTimeRange?: { start: Date; end: Date };
}

const fetchStats = async (params: StatsQueryParams): Promise<ApiResponse> => {
  let url = `/stats/summary?time_range=${params.timeRange}`;

  // Add custom time range parameters if custom is selected
  if (params.timeRange === 'custom' && params.customTimeRange) {
    url += `&start_time=${params.customTimeRange.start.toISOString()}`;
    url += `&end_time=${params.customTimeRange.end.toISOString()}`;
  }

  const response = await apiClient.get(url);
  return response.data;
};

export const useStats = (timeRange: TimeRange, customTimeRange?: { start: Date; end: Date }) => {
  const query = useQuery({
    queryKey: ['stats', timeRange, customTimeRange],
    queryFn: () => fetchStats({ timeRange, customTimeRange }),
    staleTime: 0, // 30 seconds
    gcTime: 0, // 5 minutes (formerly cacheTime)
    refetchOnWindowFocus: false,
    retry: 1,
  });

  return {
    ...query,
    refetch: query.refetch,
    isFetching: query.isFetching,
  };
};