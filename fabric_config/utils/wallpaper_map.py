"""
How busy and how bright each part of a wallpaper is, as shown on a monitor.

`build_map()` decodes the wallpaper once at reduced size, crops it the way
hyprpaper's default "cover" fit does, and reduces it to a grid of cells, each
with its mean brightness and the variance inside it. Integral sums over the
grid make any rectangle's statistics O(1), so the desktop can ask how
readable text would be anywhere (`stats()`) and search for the calmest spot
for its widgets (`calmest()`).

Brightness is Pillow's "L" (gamma-encoded luma, 0-1); `contrast_ratio()`
linearises it for WCAG-style contrast.
"""

import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gi.repository import GLib
from loguru import logger
from PIL import Image, ImageChops

# grid cells across the monitor; the grid's height follows its aspect ratio
GRID_WIDTH = 128
# resolution the variance inside each cell is measured at: fine enough to see
# the detail (ink lines, foliage, text) that makes text hard to read
DETAIL_WIDTH = 1024

Rect = tuple[float, float, float, float]  # x, y, width, height


@dataclass(frozen=True)
class RegionStats:
    mean: float  # mean brightness, 0-1
    busyness: float  # standard deviation of brightness, 0-~0.5


def _linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def contrast_ratio(text: float, background: float) -> float:
    """WCAG contrast between two gamma-encoded brightnesses (0-1)."""
    a, b = _linear(text) + 0.05, _linear(background) + 0.05
    return max(a, b) / min(a, b)


class WallpaperMap:
    def __init__(
        self,
        cells: list[list[tuple[float, float]]],
        monitor_width: int,
        monitor_height: int,
    ):
        """`cells[row][col]` is (mean, variance) of brightness in that cell."""
        self.rows = len(cells)
        self.cols = len(cells[0]) if cells else 0
        self.monitor_width = monitor_width
        self.monitor_height = monitor_height
        # integral sums of mean, mean^2 and in-cell variance, one row and
        # column of zeros in front so a rectangle is four lookups
        width = self.cols + 1
        self._sum = [0.0] * (width * (self.rows + 1))
        self._sum_sq = [0.0] * (width * (self.rows + 1))
        self._var = [0.0] * (width * (self.rows + 1))
        for r, row in enumerate(cells):
            run_sum = run_sq = run_var = 0.0
            for c, (mean, variance) in enumerate(row):
                run_sum += mean
                run_sq += mean * mean
                run_var += variance
                i = (r + 1) * width + c + 1
                above = r * width + c + 1
                self._sum[i] = self._sum[above] + run_sum
                self._sum_sq[i] = self._sum_sq[above] + run_sq
                self._var[i] = self._var[above] + run_var

    def _cells(self, rect: Rect) -> tuple[int, int, int, int]:
        """The grid cells a monitor rectangle covers: col0, row0, col1, row1."""
        x, y, w, h = rect
        sx = self.cols / self.monitor_width
        sy = self.rows / self.monitor_height
        c0 = min(max(int(x * sx), 0), self.cols - 1)
        r0 = min(max(int(y * sy), 0), self.rows - 1)
        c1 = min(max(math.ceil((x + w) * sx), c0 + 1), self.cols)
        r1 = min(max(math.ceil((y + h) * sy), r0 + 1), self.rows)
        return c0, r0, c1, r1

    def _box(self, table: list[float], c0: int, r0: int, c1: int, r1: int) -> float:
        width = self.cols + 1
        return (
            table[r1 * width + c1]
            - table[r0 * width + c1]
            - table[r1 * width + c0]
            + table[r0 * width + c0]
        )

    def _stats_cells(self, c0: int, r0: int, c1: int, r1: int) -> RegionStats:
        n = (c1 - c0) * (r1 - r0)
        mean = self._box(self._sum, c0, r0, c1, r1) / n
        between = self._box(self._sum_sq, c0, r0, c1, r1) / n - mean * mean
        within = self._box(self._var, c0, r0, c1, r1) / n
        # total variance = average variance inside the cells + variance of
        # the cell means (detail, and light/dark patches across the region)
        return RegionStats(mean, max(0.0, within + between) ** 0.5)

    def stats(self, rect: Rect) -> RegionStats:
        """Brightness statistics of a rectangle in monitor coordinates."""
        return self._stats_cells(*self._cells(rect))

    def calmest(
        self,
        width: float,
        height: float,
        bounds: Rect,
        avoid: Sequence[Rect] = (),
        score: Callable[[RegionStats, float, float], float] | None = None,
    ) -> tuple[float, float, RegionStats] | None:
        """
        The top-left corner (monitor coordinates) of the best place for a
        width x height box inside `bounds`, not overlapping `avoid`, by
        `score(stats, x, y)` (lower is better; defaults to busyness).
        """
        score = score or (lambda stats, _x, _y: stats.busyness)
        bx, by, bw, bh = bounds
        if width > bw or height > bh:
            return None
        sx = self.monitor_width / self.cols
        sy = self.monitor_height / self.rows
        best: tuple[float, float, float, RegionStats] | None = None
        # every grid-aligned position, plus the far edges of the bounds
        xs = sorted(
            {bx + bw - width}
            | {c * sx for c in range(self.cols) if bx <= c * sx <= bx + bw - width}
        )
        ys = sorted(
            {by + bh - height}
            | {r * sy for r in range(self.rows) if by <= r * sy <= by + bh - height}
        )
        for y in ys:
            for x in xs:
                if any(_overlaps((x, y, width, height), other) for other in avoid):
                    continue
                stats = self.stats((x, y, width, height))
                value = score(stats, x, y)
                if best is None or value < best[0]:
                    best = (value, x, y, stats)
        if best is None:
            return None
        return best[1], best[2], best[3]


def _overlaps(a: Rect, b: Rect) -> bool:
    return (
        a[0] < b[0] + b[2]
        and b[0] < a[0] + a[2]
        and a[1] < b[1] + b[3]
        and (b[1] < a[1] + a[3])
    )


def build_map(path: str, monitor_width: int, monitor_height: int) -> WallpaperMap:
    """Blocking: decode `path` and measure it as shown on the monitor."""
    image = Image.open(path)
    # JPEGs decode straight to a reduced size; plenty for measuring
    image.draft("L", (DETAIL_WIDTH * 2, DETAIL_WIDTH * 2))
    image = image.convert("L")

    # hyprpaper's default fit: scale to cover the monitor, centred, cropped
    aspect = monitor_width / monitor_height
    if image.width / image.height > aspect:
        crop_w = round(image.height * aspect)
        left = (image.width - crop_w) // 2
        image = image.crop((left, 0, left + crop_w, image.height))
    else:
        crop_h = round(image.width / aspect)
        top = (image.height - crop_h) // 2
        image = image.crop((0, top, image.width, top + crop_h))

    cols = GRID_WIDTH
    rows = max(1, round(cols / aspect))
    # a whole number of detail pixels per cell, so BOX averages are exact
    detail = image.resize(
        (cols * max(1, DETAIL_WIDTH // cols), rows * max(1, DETAIL_WIDTH // cols)),
        Image.Resampling.BOX,
    )
    squared = ImageChops.multiply(detail, detail)  # x*x/255
    means = detail.resize((cols, rows), Image.Resampling.BOX)
    mean_sq = squared.resize((cols, rows), Image.Resampling.BOX)

    mean_px = list(means.tobytes())
    sq_px = list(mean_sq.tobytes())
    cells = []
    for r in range(rows):
        row = []
        for c in range(cols):
            m = mean_px[r * cols + c] / 255
            sq = sq_px[r * cols + c] / 255  # E[x^2] in 0-1 units
            row.append((m, max(0.0, sq - m * m)))
        cells.append(row)
    return WallpaperMap(cells, monitor_width, monitor_height)


def build_map_async(
    path: str,
    monitor_width: int,
    monitor_height: int,
    callback: Callable[[WallpaperMap | None], None],
):
    """`build_map` on a worker thread; calls back on the main loop."""

    def work():
        try:
            result = build_map(path, monitor_width, monitor_height)
        except Exception as e:
            logger.warning(f"[Wallpaper] couldn't measure {path}: {e}")
            result = None
        GLib.idle_add(lambda: callback(result) or False)

    threading.Thread(target=work, name="wallpaper-map", daemon=True).start()
