import { KpiCard } from "../kpi-card";
import { TimeRangeSelector, TimeRange } from "../time-range-selector";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Area, AreaChart, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Loader2, RefreshCw, BarChart3, AlertCircle } from "lucide-react";
import { useStats } from "../../hooks/useStats";
import { toast } from "sonner";
interface OverviewProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange, customRange?: { start: Date; end: Date }) => void;
  customTimeRange?: { start: Date; end: Date };
}

const toTitleCase = (str: string) => {
  return str.toLowerCase().split(' ').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ');
};

export function Overview({ timeRange, onTimeRangeChange, customTimeRange }: OverviewProps) {
  const { data: apiData, isLoading: loading, error, refetch, isFetching } = useStats(timeRange, customTimeRange);

  const handleRefresh = async () => {
    try {
      await refetch();
      error ? toast.error("Failed to refresh overview data") : toast.success("Overview data refreshed successfully");
    } catch (error) {
      toast.error("Failed to refresh overview data");
    }
  };

  const hasNoData = (apiData && apiData.kpi_metrics.length === 0 && apiData.plots.length === 0);

  const renderChart = (plot: any) => {
    if (!plot) {
      return (
        <div className="flex items-center justify-center h-[300px]">
          <div className="text-sm text-muted">No data available</div>
        </div>
      );
    }

    const { plot_details } = plot;

    if (plot_details.plot_type === "pie") {
      const pieData = plot_details.data && plot_details.data.length > 0
        ? plot_details.data
        : [{ name: 'No Data', value: 100, color: '#E5E7EB' }];

      // Calculate total for center display - use count if available, otherwise sum percentages
      const total = pieData.reduce((sum: number, entry: any) => sum + (entry.count || entry.value || 0), 0);

      // Custom legend renderer
      const renderCustomLegend = () => {
        return (
          <div className="flex flex-col gap-3 mt-4">
            {pieData.map((entry: any, index: number) => (
              <div key={`legend-${index}`} className=" items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: entry.color }}
                  />
                  <span className="legend-label">{toTitleCase(entry.name)}</span>
                </div>
                <span className="legend-value" style={{ marginLeft: "15px" }}>
                  {entry.value}% ({entry.count || entry.value} requests)
                </span>
              </div>
            ))}
          </div>
        );
      };

      return (
        <div className="relative h-[280px]">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={pieData}
                cx="35%"
                cy="50%"
                innerRadius={85}
                outerRadius={95}
                paddingAngle={3}
                dataKey="value"
                startAngle={90}
                endAngle={-270}
              >
                {pieData.map((entry: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={entry.color} strokeWidth={0} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid var(--chart-border-color)',
                  borderRadius: '8px',
                  fontSize: '12px',
                  boxShadow: 'var(--chart-shadow)'
                }}
                formatter={(value: any, name: any, entry: any) => [
                  `${value}% (${entry.payload.count || value} requests)`,
                  toTitleCase(name)
                ]}
              />
            </PieChart>
          </ResponsiveContainer>

          {/* Center text - Total */}
          <div
            className="absolute text-center pointer-events-none"
            style={{
              top: '50%',
              left: '35%',
              transform: 'translate(-50%, -50%)'
            }}
          >

            <div className="pie-chart-label">{total}</div>
            <div className="pie-chart-value">Total</div>
          </div>

          {/* Custom Legend on the right */}
          <div className="absolute top-1/2 right-4 transform -translate-y-1/2 w-48">
            {renderCustomLegend()}
          </div>
        </div>
      );
    }

    if (plot_details.plot_type === "line" && plot_details.data_points) {
      const lineData = (!timeRange.includes("d") && !timeRange.includes("custom"))  ? plot_details.data_points.map((point: any) => ({
        time: new Date(point.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        value: point.value
      })) : plot_details.data_points.map((point: any) => ({
        time: new Date(point.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
        value: point.value,
      }));



      const chartColor = plot_details.color || "#22c55e";
      const gradientId = `gradient-${chartColor.replace(/\s+/g, '-')}`;

      return (
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart
            data={lineData}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            {/* <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={chartColor} stopOpacity={1} />
                <stop offset="100%" stopColor={chartColor} stopOpacity={0} />
              </linearGradient>
            </defs> */}
            <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              axisLine={true}
              tickLine={false}
              dy={10}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              axisLine={true}
              tickLine={false}
              width={40}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid var(--chart-border-color)',
                borderRadius: '8px',
                fontSize: '12px',
                boxShadow: 'var(--chart-shadow)'
              }}
              formatter={(value) => [value, plot.title]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={chartColor}
              strokeWidth={2.5}
              fill={`url(#${gradientId})`}
              dot={{
                fill: chartColor,
                strokeWidth: 2,
                r: 4,
                stroke: '#fff'
              }}
              activeDot={{
                r: 6,
                strokeWidth: 2
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      );
    }

    return (
      <div className="flex items-center justify-center h-[300px]">
        <div className="text-sm text-gray-500">Unsupported chart type</div>
      </div>
    );
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="page-title font-bold title-lg-header ">Overview</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={handleRefresh}
            disabled={isFetching}
            className="px-6 py-5 bg-card text-sm font-medium transition-colors border border-border-medium  text-muted-foreground"
            style={{ padding: "18px 22px" }}
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <TimeRangeSelector
            value={timeRange}
            onChange={onTimeRangeChange}
            customRange={customTimeRange}
          />
        </div>
      </div>

      {/* Error State */}
      {error ? (
        <div>
          <div className="p-6 space-y-6">
            <div className="flex justify-center w-full">
              <Card className="border border-border p-6 box-shadow w-full">
                <div className="flex flex-col items-center justify-center py-16 px-4">
                  <AlertCircle className="h-12 w-12 text-danger" />
                  <div className="text-center">
                    <h3 className="text-lg font-semibold text-foreground">Failed to fetch statistics data</h3>
                    <p className="text-muted-foreground mb-4">
                      {error instanceof Error ? error.message : 'Failed to load configuration'}
                    </p>
                    <Button onClick={() => handleRefresh()} variant="outline">
                      Try Again
                    </Button>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </div>
      ) : loading || isFetching ? (
        <div className="flex items-center justify-center py-16 px-4">
          <Loader2 className="h-8 w-8 animate-spin text-loading mr-3" />
          <span className="text-secondary">Loading details...</span>
        </div>
      ) : hasNoData ? (
        /* No Data State */
        <div className="flex items-center justify-center py-16 px-4">
          <div className="text-center max-w-md">
            <div className="mb-4">
              <div className="mx-auto w-16 h-16 bg-surface-secondary rounded-full flex items-center justify-center">
                <BarChart3 className="h-8 w-8 text-muted" />
              </div>
            </div>
            <h3 className="text-lg font-medium text-foreground mb-2">No Data Available</h3>
            <p className="text-secondary">
              There are no alerts in the selected time range.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* KPI Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-1 lg:grid-cols-4 gap-4">
            {apiData ? (
              // Use API data
              apiData.kpi_metrics.map((metric, index) => (
                <KpiCard
                  key={index}
                  label={metric.label}
                  value={metric.value}
                  delta={metric.delta ?? undefined}
                  tooltip={metric.tooltip}
                  className="box-shadow rounded-md"
                />
              ))
            ) : (
              // No data state
              Array.from({ length: 3 }, (_, i) => (
                <KpiCard
                  key={i}
                  label="No Data"
                  value="—"
                  delta={undefined}
                  tooltip="No data available"
                />
              ))
            )}
          </div>

          {/* Charts Section */}
          <div className="grid grid-cols-2 lg:grid-cols-2 gap-6">
            {apiData?.plots && apiData.plots.length > 0 ? (
              // Dynamically render charts based on API data
              apiData.plots.map((plot, index) => (
                <Card key={index} className="box-shadow rounded-md"  >
                  <CardHeader>
                    <CardTitle><div className="flex justify-between">
                      <div className="card-title">{plot.title}</div>
                      {plot.plot_details.plot_type === "line" && (
                        <div><span className="card-avg-label inline-flex items-center gap-1">Average
                          {/* {plot?.tooltip && (
                          <TooltipProvider>
                            <CustomTooltip>
                              <TooltipTrigger asChild>
                                <InfoIcon className="h-4 w-4 mt-1 text-muted text-xs" />
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="text-sm text-white">{plot?.tooltip}</p>
                              </TooltipContent>
                            </CustomTooltip>
                          </TooltipProvider>
                        )} */}
                        </span><p className="card-avg-value">{plot.plot_details?.average}</p></div>)}
                    </div>
                    </CardTitle>
                  </CardHeader>

                  <CardContent>
                    {renderChart(plot)}
                  </CardContent>
                </Card>
              ))
            ) : (
              // No data state
              <div className="col-span-3 flex items-center justify-center py-12">
                <div className="text-sm text-muted">No chart data available</div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}