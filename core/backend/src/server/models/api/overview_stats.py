"""
Pydantic models for Overview Statistics API endpoints.
"""
from datetime import datetime
from typing import Optional, List, Union, Annotated, Literal

from pydantic import BaseModel, Field

from .constants import DEFAULT_TIMELINE
from .enums import Status, Timeline, PlotType


class KpiMetric(BaseModel):
    """Individual KPI metric with value and delta"""
    label: str = Field(description="Display label for the metric")
    value: str = Field(description="Formatted value (e.g., '1,234', '90%', '8.4')")
    tooltip: Optional[str] = Field(default=None, description="Tooltip text for the metric")


class StatusDistributionItem(BaseModel):
    """Individual item in status distribution"""
    name: Status = Field(description="Status name")
    value: int = Field(description="Percentage value")
    count: int = Field(description="Actual count of alerts with this status")
    color: str = Field(description="Hex color code for this data item")


class TimeSeriesDataPoint(BaseModel):
    """Individual data point in time series"""
    timestamp: int = Field(description="Unix timestamp in milliseconds")
    value: Union[int, float] = Field(description="Metric value at this time point")


class PieChartDetail(BaseModel):
    """Configuration for pie chart"""
    plot_type: Literal[PlotType.PIE] = Field(default=PlotType.PIE, description="Plot type identifier")
    data: List[StatusDistributionItem] = Field(description="Pie chart data items")


class LineChartDetail(BaseModel):
    """Configuration for line chart"""
    plot_type: Literal[PlotType.LINE] = Field(default=PlotType.LINE, description="Plot type identifier")
    data_points: List[TimeSeriesDataPoint] = Field(description="List of time series data points")
    color: Optional[str] = Field(default=None, description="Line color")
    show_dots: bool = Field(default=True, description="Whether to show data point dots")
    average: Optional[str] = Field(default=None, description="Average value across all data points")


# Union type for plot details with discriminator
PlotDetailUnion = Annotated[Union[PieChartDetail, LineChartDetail], Field(discriminator='plot_type')]


class PlotConfig(BaseModel):
    """Individual plot configuration"""
    title: str = Field(description="Plot title")
    plot_details: PlotDetailUnion = Field(description="Plot-specific configuration")
    tooltip: Optional[str] = Field(default=None, description="Tooltip text for the plot")


class OverviewStatsRequest(BaseModel):
    """Request model for GET /v1/overview/stats (Query Parameters)"""
    time_range: Timeline = Field(default=DEFAULT_TIMELINE, description="Time range for statistics")
    # Custom time range fields
    start_time: Optional[datetime] = Field(default=None, description="Custom range start time (ISO 8601 with timezone)")
    end_time: Optional[datetime] = Field(default=None, description="Custom range end time (ISO 8601 with timezone)")


class OverviewStatsResponse(BaseModel):
    """Response for overview statistics endpoint"""
    kpi_metrics: List[KpiMetric] = Field(description="Ordered list of KPI metrics to display")
    plots: List[PlotConfig] = Field(description="Ordered list of plots to render")
