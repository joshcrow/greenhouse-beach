"""Greenhouse Gazette Weather Dashboard Generator.

Production chart generator for the Greenhouse Gazette email newsletter.
Optimized for Raspberry Pi 5 performance.

Usage:
    # Direct generation
    from chart_generator import generate_weather_dashboard
    png_bytes = generate_weather_dashboard(hours=24)  # Daily
    png_bytes = generate_weather_dashboard(hours=168) # Weekly
    
    # Publisher.py compatibility
    from chart_generator import generate_temperature_chart
    png_bytes = generate_temperature_chart(hours=24)

Design System ("Professional Industrial"):
    Background:     #171717 (Neutral 900)
    Inside/Hero:    #6b9b5a (Greenhouse Green)
    Outside/Context:#60a5fa (Blue)
    Text Primary:   #f5f5f5
    Text Muted:     #a3a3a3

Visual Features:
    - Header with H/L stats for both sensors
    - Temperature panel: buffer fill between lines shows insulation effect
    - Humidity panel: buffer fill between lines shows moisture differential
    - Dashed grid lines for technical aesthetic
    - Dynamic x-axis: time (daily) or day names (weekly)

Performance:
    - Lazy imports (matplotlib/numpy/scipy)
    - Smart downsampling for weekly view (>48h → hourly averages)
    - 200 DPI output optimized for email/mobile
"""

import io
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Lazy imports to reduce startup time on Pi
_plt = None
_mdates = None
_np = None


def _get_imports():
    """Lazy-load matplotlib and numpy."""
    global _plt, _mdates, _np
    if _plt is None:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import numpy as np
        _plt = plt
        _mdates = mdates
        _np = np
    return _plt, _mdates, _np


def log(msg: str) -> None:
    """Simple logging with timestamp."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [chart] {msg}")


# =============================================================================
# GREENHOUSE GAZETTE THEME (Matches Email CSS Exactly)
# =============================================================================
# Design System: "Professional Industrial" - specialized greenhouse monitoring console
# All colors match the email CSS dark mode variables for visual consistency
THEME = {
    "bg": "#171717",              # CSS: --bg-dark (Neutral 900)
    "text_main": "#f5f5f5",       # CSS: --text-primary-dark (Neutral 50)
    "text_muted": "#a3a3a3",      # CSS: --text-muted-dark (Neutral 400)
    "grid_color": "#6b9b5a",      # CSS: --accent (Greenhouse Green)
    "grid_alpha": 0.10,           # Very subtle grid lines
    "inside_temp": "#6b9b5a",     # CSS: --accent (The Hero - Greenhouse Green)
    "outside_temp": "#60a5fa",    # CSS: --temp-low-dark (The Context - Blue)
    "inside_humidity": "#6b9b5a", # CSS: --accent (Greenhouse Green)
    "outside_humidity": "#a3a3a3",# CSS: --text-muted-dark (Muted context)
}

# Sensor key mappings
SENSOR_MAPPINGS = {
    "temp": {
        "Inside": "exterior_temp",
        "Outside": "satellite-2_temperature",
    },
    "humidity": {
        "Inside": "exterior_humidity",
        "Outside": "satellite-2_humidity",
    },
}


# =============================================================================
# DATA LOADING & PROCESSING
# =============================================================================

def _load_sensor_data(hours: int = 24) -> List[Dict[str, Any]]:
    """Load sensor readings from the log directory.
    
    Sensor logs are stored as JSONL files in a directory structure:
    /app/data/sensor_log/YYYY-MM.jsonl
    """
    log_dir = os.environ.get("SENSOR_LOG_PATH", "/app/data/sensor_log")
    
    if not os.path.exists(log_dir):
        log(f"Sensor log directory not found: {log_dir}")
        return []
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    readings = []
    
    # Find all JSONL files in the directory
    try:
        if os.path.isdir(log_dir):
            files = sorted([
                os.path.join(log_dir, f) 
                for f in os.listdir(log_dir) 
                if f.endswith('.jsonl')
            ])
        else:
            # Single file fallback
            files = [log_dir]
        
        for file_path in files:
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            # Handle both "ts" and "timestamp" keys
                            ts_str = entry.get("ts") or entry.get("timestamp")
                            if ts_str:
                                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                if ts.replace(tzinfo=None) >= cutoff:
                                    # Flatten nested "sensors" structure if present
                                    if "sensors" in entry:
                                        flat = {"timestamp": ts_str}
                                        flat.update(entry["sensors"])
                                        readings.append(flat)
                                    else:
                                        readings.append(entry)
                        except (json.JSONDecodeError, ValueError):
                            continue
            except Exception as e:
                log(f"Error reading {file_path}: {e}")
                continue
    except Exception as e:
        log(f"Error listing sensor log directory: {e}")
    
    log(f"Loaded {len(readings)} readings from {len(files)} file(s)")
    return readings


def _extract_series(
    readings: List[Dict[str, Any]],
    key_mapping: Dict[str, str],
) -> Dict[str, Tuple[List[datetime], List[float]]]:
    """Extract time series for each sensor key."""
    series = {name: ([], []) for name in key_mapping}
    
    for entry in readings:
        ts_str = entry.get("timestamp")
        if not ts_str:
            continue
        
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            continue
        
        for name, key in key_mapping.items():
            value = entry.get(key)
            if value is not None:
                try:
                    val = float(value)
                    # Sanity check (per project rules: -10 to 130°F)
                    if -10 <= val <= 130 or key.endswith('humidity'):
                        series[name][0].append(ts)
                        series[name][1].append(val)
                except (ValueError, TypeError):
                    continue
    
    return series


def _resample_to_hourly(
    timestamps: List[datetime],
    values: List[float],
) -> Tuple[List[datetime], List[float]]:
    """Resample 5-minute data to 1-hour averages for Pi optimization.
    
    Reduces ~2000 points to ~168 points for weekly charts.
    Gaps in data result in gaps in output (no interpolation across outages).
    """
    if len(timestamps) < 2:
        return timestamps, values
    
    _, _, np = _get_imports()
    
    # Group by hour
    hourly_bins: Dict[datetime, List[float]] = {}
    
    for ts, val in zip(timestamps, values):
        # Round down to hour
        hour_key = ts.replace(minute=0, second=0, microsecond=0)
        if hour_key not in hourly_bins:
            hourly_bins[hour_key] = []
        hourly_bins[hour_key].append(val)
    
    # Calculate averages
    resampled_ts = []
    resampled_vals = []
    
    for hour_key in sorted(hourly_bins.keys()):
        bin_values = hourly_bins[hour_key]
        if bin_values:
            resampled_ts.append(hour_key + timedelta(minutes=30))  # Center of hour
            resampled_vals.append(np.mean(bin_values))
    
    return resampled_ts, resampled_vals


def _smooth_curve(x, y, num_points: int = 300, gentle: bool = False):
    """Create smooth curve using monotonic spline (prevents overshoot).
    
    Args:
        x: X values (numeric)
        y: Y values
        num_points: Number of interpolation points
        gentle: If True, use simpler linear interpolation (less boxy for stable data)
    """
    _, _, np = _get_imports()
    
    if len(x) < 2:
        return np.array(x), np.array(y)
    
    x_arr = np.array(x)
    y_arr = np.array(y)
    
    # Remove duplicate x values
    _, unique_idx = np.unique(x_arr, return_index=True)
    x_arr = x_arr[unique_idx]
    y_arr = y_arr[unique_idx]
    
    if len(x_arr) < 2:
        return x_arr, y_arr
    
    x_smooth = np.linspace(x_arr.min(), x_arr.max(), num_points)
    
    try:
        if gentle:
            # Simple linear interpolation - more organic for stable/flat data
            from scipy.interpolate import interp1d
            interp = interp1d(x_arr, y_arr, kind='linear', fill_value='extrapolate')
            y_smooth = interp(x_smooth)
        else:
            # PCHIP for daily view - smooth but monotonic
            from scipy.interpolate import PchipInterpolator
            spline = PchipInterpolator(x_arr, y_arr)
            y_smooth = spline(x_smooth)
        return x_smooth, y_smooth
    except Exception:
        return x_arr, y_arr


def _find_min_max_points(x_smooth, y_smooth):
    """Find the x,y coordinates of min and max values."""
    _, _, np = _get_imports()
    
    if len(y_smooth) == 0:
        return None, None
    
    min_idx = np.argmin(y_smooth)
    max_idx = np.argmax(y_smooth)
    
    return (x_smooth[min_idx], y_smooth[min_idx]), (x_smooth[max_idx], y_smooth[max_idx])


# =============================================================================
# MAIN CHART GENERATOR
# =============================================================================

def generate_weather_dashboard(
    hours: int = 24,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """Generate a production-ready weather dashboard chart.
    
    "Protection & Performance" design featuring:
    - Temperature panel with buffer fill BETWEEN lines (insulation visualization)
    - 32°F danger zone reference line (conditional)
    - Clean humidity panel (lines only, no fills)
    - Stat badges with rounded rectangles
    - Smart downsampling for weekly data
    
    Args:
        hours: Duration of data to display (24 for daily, 168 for weekly)
        output_path: Optional path to save PNG file
    
    Returns:
        PNG image bytes, or None if generation fails
    """
    try:
        plt, mdates, np = _get_imports()
        from scipy.interpolate import interp1d
    except ImportError as exc:
        log(f"Required libraries not available: {exc}")
        return None
    
    # Load sensor data
    readings = _load_sensor_data(hours)
    if len(readings) < 2:
        log(f"Insufficient data for chart: {len(readings)} readings")
        return None
    
    # Extract series
    temp_series = _extract_series(readings, SENSOR_MAPPINGS["temp"])
    humidity_series = _extract_series(readings, SENSOR_MAPPINGS["humidity"])
    
    if not any(len(s[0]) > 1 for s in temp_series.values()):
        log("No valid temperature data")
        return None
    
    # Smart downsampling for weekly charts (Pi optimization)
    if hours > 48:
        log(f"Resampling {hours}h data to hourly averages...")
        for name in temp_series:
            ts, vals = temp_series[name]
            if len(ts) > 0:
                temp_series[name] = _resample_to_hourly(ts, vals)
        for name in humidity_series:
            ts, vals = humidity_series[name]
            if len(ts) > 0:
                humidity_series[name] = _resample_to_hourly(ts, vals)
    
    # Brand colors (strict adherence)
    COLOR_GREEN = "#6b9b5a"  # Inside - The Hero (Greenhouse Green)
    COLOR_BLUE = "#60a5fa"   # Outside - The Context
    COLOR_BG = "#171717"     # Background
    
    # Create figure with dedicated header space
    # Using GridSpec for precise control: header row + temp + humidity
    fig = plt.figure(figsize=(8, 5.5), dpi=200)
    gs = fig.add_gridspec(
        3, 1,
        height_ratios=[0.12, 3, 2],  # Header, Temp, Humidity
        hspace=0.08,
        left=0.08, right=0.97, top=0.98, bottom=0.10
    )
    
    ax_header = fig.add_subplot(gs[0])  # Dedicated header area
    ax_temp = fig.add_subplot(gs[1])
    ax_humid = fig.add_subplot(gs[2], sharex=ax_temp)
    
    # Hide header axes (just for text placement)
    ax_header.set_facecolor(COLOR_BG)
    ax_header.axis('off')
    
    fig.patch.set_facecolor(COLOR_BG)
    ax_temp.set_facecolor(COLOR_BG)
    ax_humid.set_facecolor(COLOR_BG)
    
    # Determine if weekly view (affects smoothing)
    is_weekly = hours > 48
    
    # =========================================
    # TOP PANEL: "Protection" (Temperature)
    # =========================================
    temp_smoothed = {}
    temp_stats = {}
    
    for name, (timestamps, values) in temp_series.items():
        if len(timestamps) < 2:
            continue
        
        x_numeric = mdates.date2num(timestamps)
        # Use gentler smoothing for weekly view to avoid boxy artifacts
        x_smooth, y_smooth = _smooth_curve(x_numeric, values, num_points=300, gentle=is_weekly)
        temp_smoothed[name] = (x_smooth, y_smooth)
        
        current = values[-1] if values else 0
        high = max(values) if values else 0
        low = min(values) if values else 0
        temp_stats[name] = {"current": current, "high": high, "low": low}
    
    # Compute global x range
    all_x = []
    for name, (timestamps, _) in temp_series.items():
        if timestamps:
            all_x.extend(mdates.date2num(timestamps))
    for name, (timestamps, _) in humidity_series.items():
        if timestamps:
            all_x.extend(mdates.date2num(timestamps))
    
    global_x_min = min(all_x) if all_x else 0
    global_x_max = max(all_x) if all_x else 1
    
    # Dynamic Y-axis for temperature (header is separate, less padding needed)
    all_temps = []
    for name, (_, values) in temp_series.items():
        all_temps.extend(values)
    if all_temps:
        t_min, t_max = min(all_temps), max(all_temps)
        t_range = t_max - t_min
        t_padding_bottom = max(t_range * 0.08, 2)
        t_padding_top = max(t_range * 0.12, 4)  # Less padding - header is separate
        temp_y_min = t_min - t_padding_bottom
        temp_y_max = t_max + t_padding_top
        ax_temp.set_ylim(temp_y_min, temp_y_max)
    else:
        temp_y_min, temp_y_max = 0, 100
    
    # Plot "Buffer Fill" BETWEEN lines (insulation/heat buffer visualization)
    if "Inside" in temp_smoothed and "Outside" in temp_smoothed:
        x_in, y_in = temp_smoothed["Inside"]
        x_out, y_out = temp_smoothed["Outside"]
        
        # Interpolate to common x grid
        x_common = np.linspace(global_x_min, global_x_max, 400)
        try:
            y_in_interp = interp1d(x_in, y_in, kind='linear', fill_value='extrapolate')(x_common)
            y_out_interp = interp1d(x_out, y_out, kind='linear', fill_value='extrapolate')(x_common)
            
            # Fill the "protection buffer" where Inside > Outside (green)
            # Reduced alpha (0.15) so trend lines remain prominent
            ax_temp.fill_between(
                x_common, y_out_interp, y_in_interp,
                where=(y_in_interp >= y_out_interp),
                color=COLOR_GREEN,
                alpha=0.15,
                interpolate=True,
                zorder=1,
            )
        except Exception as e:
            log(f"Buffer fill error: {e}")
    
    # Plot temperature lines
    # Outside first (context, thinner)
    if "Outside" in temp_smoothed:
        x, y = temp_smoothed["Outside"]
        ax_temp.plot(x, y, color=COLOR_BLUE, linewidth=1.5, solid_capstyle='round', zorder=2)
    
    # Inside on top (hero, thicker)
    if "Inside" in temp_smoothed:
        x, y = temp_smoothed["Inside"]
        ax_temp.plot(x, y, color=COLOR_GREEN, linewidth=2.5, solid_capstyle='round', zorder=3)
    
    # =========================================
    # BOTTOM PANEL: "Response" (Humidity)
    # =========================================
    humidity_smoothed = {}
    humidity_stats = {}
    
    for name, (timestamps, values) in humidity_series.items():
        if len(timestamps) < 2:
            continue
        
        x_numeric = mdates.date2num(timestamps)
        # Use gentler smoothing for weekly view
        x_smooth, y_smooth = _smooth_curve(x_numeric, values, num_points=300, gentle=is_weekly)
        humidity_smoothed[name] = (x_smooth, y_smooth)
        
        current = values[-1] if values else 0
        high = max(values) if values else 0
        low = min(values) if values else 0
        humidity_stats[name] = {"current": current, "high": high, "low": low}
    
    # Dynamic Y-axis for humidity (header is separate, less padding needed)
    all_humid = []
    for name, (_, values) in humidity_series.items():
        all_humid.extend(values)
    if all_humid:
        h_min, h_max = min(all_humid), max(all_humid)
        h_range = h_max - h_min
        h_padding_bottom = max(h_range * 0.08, 2)
        h_padding_top = max(h_range * 0.12, 4)  # Less padding - header is separate
        humid_y_min = max(0, h_min - h_padding_bottom)
        humid_y_max = min(100, h_max + h_padding_top)
        ax_humid.set_ylim(humid_y_min, humid_y_max)
    else:
        humid_y_min = 0
    
    # Plot "Buffer Fill" BETWEEN humidity lines (same as temperature)
    if "Inside" in humidity_smoothed and "Outside" in humidity_smoothed:
        x_in, y_in = humidity_smoothed["Inside"]
        x_out, y_out = humidity_smoothed["Outside"]
        
        # Interpolate to common x grid
        x_common = np.linspace(global_x_min, global_x_max, 400)
        try:
            y_in_interp = interp1d(x_in, y_in, kind='linear', fill_value='extrapolate')(x_common)
            y_out_interp = interp1d(x_out, y_out, kind='linear', fill_value='extrapolate')(x_common)
            
            # Fill between lines (green where inside > outside)
            ax_humid.fill_between(
                x_common, y_out_interp, y_in_interp,
                where=(y_in_interp >= y_out_interp),
                color=COLOR_GREEN,
                alpha=0.15,
                interpolate=True,
                zorder=1,
            )
            # Fill where outside > inside (blue)
            ax_humid.fill_between(
                x_common, y_in_interp, y_out_interp,
                where=(y_out_interp > y_in_interp),
                color=COLOR_BLUE,
                alpha=0.10,
                interpolate=True,
                zorder=1,
            )
        except Exception as e:
            log(f"Humidity buffer fill error: {e}")
    
    # Plot humidity lines
    if "Outside" in humidity_smoothed:
        x, y = humidity_smoothed["Outside"]
        ax_humid.plot(x, y, color=COLOR_BLUE, linewidth=1.5, solid_capstyle='round', zorder=2)
    
    if "Inside" in humidity_smoothed:
        x, y = humidity_smoothed["Inside"]
        ax_humid.plot(x, y, color=COLOR_GREEN, linewidth=2.0, solid_capstyle='round', zorder=3)
    
    # =========================================
    # HEADER STATS (Dedicated area above charts)
    # =========================================
    # Badge styling for header
    badge_props_inside = dict(
        boxstyle='round,pad=0.5,rounding_size=0.4',
        facecolor=COLOR_GREEN,
        edgecolor='none',
        alpha=0.95,
    )
    # Outside: High contrast - solid background for readability
    badge_props_outside = dict(
        boxstyle='round,pad=0.5,rounding_size=0.4',
        facecolor='#1f2937',  # Slightly lighter than bg for contrast
        edgecolor=COLOR_BLUE,
        linewidth=1.5,
        alpha=0.95,
    )
    
    # Temperature header - H/L only (no current temps)
    if "Inside" in temp_stats:
        s = temp_stats["Inside"]
        ax_header.text(
            0.01, 0.5,
            f"● Inside  H:{int(round(s['high']))}° L:{int(round(s['low']))}°",
            transform=ax_header.transAxes,
            fontsize=11,
            fontweight='bold',
            color='white',
            ha='left',
            va='center',
            bbox=badge_props_inside,
        )
    
    if "Outside" in temp_stats:
        s = temp_stats["Outside"]
        ax_header.text(
            0.99, 0.5,
            f"○ Outside  H:{int(round(s['high']))}° L:{int(round(s['low']))}°",
            transform=ax_header.transAxes,
            fontsize=11,
            fontweight='bold',
            color='#93c5fd',
            ha='right',
            va='center',
            bbox=badge_props_outside,
        )
    
    # =========================================
    # X-AXIS: Full width
    # =========================================
    ax_humid.set_xlim(global_x_min, global_x_max)
    
    # =========================================
    # STYLING
    # =========================================
    for ax in [ax_temp, ax_humid]:
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # Dashed grid for technical/precision look
        ax.yaxis.grid(
            True,
            linestyle='--',
            alpha=0.15,
            color='white',
            linewidth=0.5,
        )
        ax.xaxis.grid(False)
        ax.set_axisbelow(True)
        
        ax.tick_params(
            axis='both',
            colors=THEME["text_muted"],
            labelsize=11,
            length=0,
            pad=6,
        )
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(4, integer=True))
    
    # Hide x-axis labels on temperature panel (shared axis - only show on bottom)
    ax_temp.tick_params(axis='x', labelbottom=False)
    
    # Y-axis formatters
    ax_temp.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x)}°"))
    ax_humid.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x)}%"))
    
    # Dynamic X-axis formatting (only on humidity panel)
    if hours <= 48:
        ax_humid.xaxis.set_major_formatter(mdates.DateFormatter('%-I%p'))
        ax_humid.xaxis.set_major_locator(mdates.HourLocator(interval=4 if hours <= 24 else 8))
    else:
        ax_humid.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
        ax_humid.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    
    ax_humid.tick_params(axis='x', labelsize=12)
    
    # Save
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format='png',
        facecolor=COLOR_BG,
        edgecolor='none',
        dpi=200,
        bbox_inches='tight',
        pad_inches=0.15,  # Extra padding for legend breathing room
    )
    plt.close(fig)
    buf.seek(0)
    png_bytes = buf.read()
    
    # Optionally save to file
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(png_bytes)
        log(f"Saved: {output_path} ({len(png_bytes)} bytes)")
    
    log(f"Generated weather dashboard ({hours}h): {len(png_bytes)} bytes")
    return png_bytes


# =============================================================================
# PUBLISHER.PY COMPATIBILITY API
# =============================================================================

def generate_temperature_chart(hours: int = 24) -> Optional[bytes]:
    """Generate temperature chart for email embedding.
    
    This is the public API used by publisher.py. It delegates to the
    full dashboard generator which includes both temperature and humidity.
    
    Args:
        hours: Duration to display (24 for daily, 168 for weekly)
    
    Returns:
        PNG image bytes, or None if generation fails
    """
    return generate_weather_dashboard(hours=hours)


# =============================================================================
# MAIN BLOCK FOR TESTING
# =============================================================================

if __name__ == "__main__":
    import sys
    
    log("=" * 50)
    log("Weather Dashboard Generator - Test Run")
    log("=" * 50)
    
    # Determine output directory
    output_dir = "/app/data" if os.path.exists("/app/data") else "/tmp"
    
    # Generate daily chart (24 hours)
    log("Generating daily dashboard (24h)...")
    daily = generate_weather_dashboard(
        hours=24,
        output_path=os.path.join(output_dir, "dashboard_daily.png"),
    )
    
    if daily:
        log(f"✓ Daily dashboard: {len(daily)} bytes")
    else:
        log("✗ Daily dashboard failed")
        sys.exit(1)
    
    # Generate weekly chart (7 days = 168 hours)
    log("Generating weekly dashboard (7d)...")
    weekly = generate_weather_dashboard(
        hours=168,
        output_path=os.path.join(output_dir, "dashboard_weekly.png"),
    )
    
    if weekly:
        log(f"✓ Weekly dashboard: {len(weekly)} bytes")
    else:
        log("✗ Weekly dashboard failed")
        sys.exit(1)
    
    log("=" * 50)
    log("All tests passed!")
    log(f"Output files in: {output_dir}")
    log("=" * 50)
