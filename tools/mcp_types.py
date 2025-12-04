"""
MCP Common Types and Enums

Provides shared types for MCP tool responses including:
- ResponseFormat enum for JSON/Markdown output
- Base response models
- Pagination models
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field


class ResponseFormat(str, Enum):
    """
    Output format for tool responses.

    JSON: Machine-readable structured data (default)
    MARKDOWN: Human-readable formatted text for display
    """
    JSON = "json"
    MARKDOWN = "markdown"


class PaginationInfo(BaseModel):
    """
    Pagination metadata for list responses.

    Follows MCP best practice for paginated results.
    """
    total: int = Field(description="Total number of items available")
    count: int = Field(description="Number of items returned in this page")
    offset: int = Field(description="Number of items skipped")
    limit: int = Field(description="Maximum items per page")
    has_more: bool = Field(description="Whether more items are available")
    next_offset: Optional[int] = Field(
        default=None,
        description="Offset for next page, None if no more pages"
    )


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.

    Usage:
        PaginatedResponse[JobInfo](items=[...], pagination=...)
    """
    items: List[Any] = Field(description="List of items in this page")
    pagination: PaginationInfo = Field(description="Pagination metadata")


class BaseToolInput(BaseModel):
    """
    Base class for tool inputs with common fields.

    All IX tool input models should inherit from this to get
    response_format support automatically.
    """
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="Output format: 'json' for machine-readable or 'markdown' for human-readable"
    )

    class Config:
        use_enum_values = True


def format_as_markdown(data: Dict[str, Any], title: str = "Results") -> str:
    """
    Convert structured data to markdown format.

    Args:
        data: Dictionary to format
        title: Title for the markdown document

    Returns:
        Markdown-formatted string
    """
    lines = [f"# {title}", ""]

    def format_value(value: Any, indent: int = 0) -> str:
        """Recursively format values."""
        prefix = "  " * indent

        if isinstance(value, dict):
            result = []
            for k, v in value.items():
                formatted_key = k.replace("_", " ").title()
                if isinstance(v, (dict, list)):
                    result.append(f"{prefix}- **{formatted_key}**:")
                    result.append(format_value(v, indent + 1))
                else:
                    result.append(f"{prefix}- **{formatted_key}**: {v}")
            return "\n".join(result)

        elif isinstance(value, list):
            if not value:
                return f"{prefix}(empty)"
            result = []
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    result.append(f"{prefix}{i + 1}.")
                    result.append(format_value(item, indent + 1))
                else:
                    result.append(f"{prefix}- {item}")
            return "\n".join(result)

        else:
            return f"{prefix}{value}"

    # Format top-level sections
    for key, value in data.items():
        formatted_key = key.replace("_", " ").title()

        if key in ["error", "status"] and value == "error":
            lines.append(f"## Error")
            continue

        if isinstance(value, dict):
            lines.append(f"## {formatted_key}")
            lines.append("")
            lines.append(format_value(value))
            lines.append("")

        elif isinstance(value, list):
            lines.append(f"## {formatted_key}")
            lines.append("")
            lines.append(format_value(value))
            lines.append("")

        else:
            # Format numbers nicely
            if isinstance(value, float):
                if abs(value) < 0.01 or abs(value) > 10000:
                    formatted_value = f"{value:.3e}"
                else:
                    formatted_value = f"{value:.3f}"
            else:
                formatted_value = str(value)
            lines.append(f"- **{formatted_key}**: {formatted_value}")

    return "\n".join(lines)


def format_vessel_config_markdown(config: Dict[str, Any]) -> str:
    """
    Format vessel configuration as markdown table.

    Args:
        config: Vessel configuration dictionary

    Returns:
        Markdown table string
    """
    lines = [
        "## Vessel Configuration",
        "",
        "| Parameter | Value | Unit |",
        "|-----------|-------|------|"
    ]

    unit_map = {
        "diameter_m": "m",
        "bed_depth_m": "m",
        "vessel_height_m": "m",
        "freeboard_m": "m",
        "bed_volume_L": "L",
        "resin_volume_m3": "m³",
        "linear_velocity_m_hr": "m/hr",
        "service_flow_bv_hr": "BV/hr",
        "number_service": "-",
        "number_standby": "-",
        "bed_expansion_percent": "%",
    }

    for key, value in config.items():
        if key.startswith("_"):
            continue

        formatted_key = key.replace("_", " ").title()
        unit = unit_map.get(key, "-")

        if isinstance(value, float):
            formatted_value = f"{value:.2f}"
        else:
            formatted_value = str(value)

        lines.append(f"| {formatted_key} | {formatted_value} | {unit} |")

    return "\n".join(lines)


def format_economics_markdown(economics: Dict[str, Any]) -> str:
    """
    Format economics data as markdown.

    Args:
        economics: Economics dictionary with CAPEX, OPEX, LCOW

    Returns:
        Markdown formatted string
    """
    lines = [
        "## Economic Analysis",
        "",
        "### Capital Costs (CAPEX)",
        "",
        "| Item | Cost (USD) |",
        "|------|------------|"
    ]

    capex = economics.get("capex", {})
    for key, value in capex.items():
        formatted_key = key.replace("_", " ").title()
        lines.append(f"| {formatted_key} | ${value:,.0f} |")

    lines.extend([
        "",
        "### Operating Costs (OPEX)",
        "",
        "| Item | Cost (USD/year) |",
        "|------|-----------------|"
    ])

    opex = economics.get("opex", {})
    for key, value in opex.items():
        formatted_key = key.replace("_", " ").title()
        lines.append(f"| {formatted_key} | ${value:,.0f} |")

    lcow = economics.get("lcow_usd_m3", 0)
    lines.extend([
        "",
        f"### Levelized Cost of Water: **${lcow:.3f}/m³**",
    ])

    return "\n".join(lines)
