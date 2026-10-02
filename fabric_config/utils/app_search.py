import ast
import json
import math
import operator
import os
import time
import unicodedata
from dataclasses import dataclass, field
from functools import cache

from fabric.utils import DesktopApp, get_desktop_applications
from gi.repository import GLib
from loguru import logger
from thefuzz import fuzz

APP_CACHE = os.path.join(GLib.get_user_cache_dir(), "fabric", "app_launcher")
STATS_FILE = os.path.join(APP_CACHE, "app_stats.json")
LEGACY_RECENT_FILE = os.path.join(APP_CACHE, "last_launched.json")

# A launch loses half its weight every two weeks
FRECENCY_HALF_LIFE = 14 * 24 * 60 * 60


@dataclass
class AppEntry:
    app: DesktopApp
    id: str
    name: str
    description: str
    keywords: list[str]
    actions: list[tuple[str, str]]  # (action id, label)
    # lowercase fields searched after the name, most relevant first
    extra_fields: list[str] = field(default_factory=list)

    @classmethod
    def from_app(cls, app: DesktopApp) -> "AppEntry":
        info = app._app
        keywords = [k for k in (info.get_keywords() or []) if k]
        categories = [c for c in (info.get_categories() or "").split(";") if c]
        actions = [(a, info.get_action_name(a)) for a in info.list_actions()]
        name = app.display_name or app.name
        app_id = info.get_id() or name
        extra = [
            app.generic_name or "",
            *keywords,
            os.path.basename(app.executable or ""),
            app_id.removesuffix(".desktop"),
            *categories,
        ]
        return cls(
            app=app,
            id=app_id,
            name=name,
            description=app.description or app.generic_name or "",
            keywords=keywords,
            actions=actions,
            extra_fields=[f.lower() for f in extra if f],
        )


def load_entries() -> list[AppEntry]:
    entries = [AppEntry.from_app(app) for app in get_desktop_applications()]
    return sorted(entries, key=lambda e: e.name.lower())


def _word_starts_with(text: str, query: str) -> bool:
    return any(word.startswith(query) for word in text.replace("-", " ").split())


def match_score(query: str, entry: AppEntry) -> float:
    """
    How well `query` (lowercase, stripped) matches `entry`; 0 means no match.
    Prefix matches on the name beat matches buried inside it, which beat
    matches on keywords, executable and categories, which beat fuzzy matches.
    """
    name = entry.name.lower()
    if name == query:
        return 100
    if name.startswith(query):
        return 90
    if _word_starts_with(name, query):
        return 80
    if any(
        f.startswith(query) or _word_starts_with(f, query) for f in entry.extra_fields
    ):
        return 70
    if query in name:
        return 60
    if any(query in f for f in entry.extra_fields):
        return 50
    # tolerate typos, but only once there is enough to go on
    if len(query) >= 3:
        ratio = fuzz.partial_ratio(query, name)
        if ratio >= 75:
            return ratio * 0.5
    return 0


class AppStats:
    """
    Launch counts, pins and hidden apps, persisted to STATS_FILE and keyed by
    desktop file id.
    """

    def __init__(self):
        self.launches: dict[str, dict[str, float]] = {}
        self.pinned: list[str] = []
        self.hidden: list[str] = []
        self._load()

    def _load(self):
        try:
            with open(STATS_FILE) as f:
                data = json.load(f)
            self.launches = dict(data.get("launches", {}))
            self.pinned = list(data.get("pinned", []))
            self.hidden = list(data.get("hidden", []))
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            logger.warning(f"[App Menu] Ignoring corrupted stats file: {e}")

    def migrate_legacy(self, entries: list[AppEntry]):
        """Import the old most-recent-first list of display names, once."""
        if self.launches or not os.path.exists(LEGACY_RECENT_FILE):
            return
        try:
            with open(LEGACY_RECENT_FILE) as f:
                names = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        by_name = {e.name: e.id for e in entries}
        now = time.time()
        for i, name in enumerate(names if isinstance(names, list) else []):
            if name in by_name:
                # keep the old order: earlier entries count as more recent
                self.launches[by_name[name]] = {"count": 1, "last": now - i * 60}
        self.save()

    def save(self):
        os.makedirs(APP_CACHE, exist_ok=True)
        tmp = STATS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(
                {
                    "launches": self.launches,
                    "pinned": self.pinned,
                    "hidden": self.hidden,
                },
                f,
            )
        os.replace(tmp, STATS_FILE)

    def record_launch(self, app_id: str):
        stat = self.launches.setdefault(app_id, {"count": 0, "last": 0})
        stat["count"] += 1
        stat["last"] = time.time()
        self.save()

    def frecency(self, app_id: str) -> float:
        stat = self.launches.get(app_id)
        if not stat:
            return 0
        age = max(0.0, time.time() - stat.get("last", 0))
        return stat.get("count", 0) * 0.5 ** (age / FRECENCY_HALF_LIFE)

    def top(self, limit: int) -> list[str]:
        ranked = sorted(self.launches, key=self.frecency, reverse=True)
        return [i for i in ranked if self.frecency(i) > 0][:limit]

    def toggle(self, collection: list[str], app_id: str):
        if app_id in collection:
            collection.remove(app_id)
        else:
            collection.append(app_id)
        self.save()


# Calculator ("=" prefix)

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}
_FUNCTIONS = {
    name: getattr(math, name)
    for name in (
        "sqrt", "cbrt", "exp", "log", "log2", "log10", "sin", "cos", "tan",
        "asin", "acos", "atan", "sinh", "cosh", "tanh", "degrees", "radians",
        "floor", "ceil", "factorial", "gcd", "lcm", "hypot",
    )
} | {"abs": abs, "round": round, "min": min, "max": max}  # fmt: skip


def _eval_node(node: ast.AST) -> float:
    match node:
        case ast.Expression(body=body):
            return _eval_node(body)
        case ast.Constant(value=value) if isinstance(value, (int, float)):
            return value
        case ast.Name(id=name) if name in _CONSTANTS:
            return _CONSTANTS[name]
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _UNARY_OPS:
            return _UNARY_OPS[type(op)](_eval_node(operand))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BIN_OPS:
            lhs, rhs = _eval_node(left), _eval_node(right)
            if isinstance(op, ast.Pow) and abs(rhs) > 10_000:
                raise ValueError("exponent too large")
            return _BIN_OPS[type(op)](lhs, rhs)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if (
            name in _FUNCTIONS
        ):
            values = [_eval_node(a) for a in args]
            if name == "factorial" and values and values[0] > 1000:
                raise ValueError("factorial argument too large")
            return _FUNCTIONS[name](*values)
    raise ValueError("unsupported expression")


def calculate(expression: str) -> str | None:
    """Evaluate a math expression, or return None if it isn't one."""
    try:
        # people type 2^8 meaning a power; as Python's xor it would bind looser than +
        expression = expression.replace("^", "**").replace("×", "*")
        result = _eval_node(ast.parse(expression, mode="eval"))
        if isinstance(result, float):
            if result.is_integer() and abs(result) < 1e15:
                return str(int(result))
            return f"{result:.10g}"
        # ValueError past Python's int-to-str digit limit
        return str(result)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


# Emoji (":" prefix)

_EMOJI_RANGES = [
    (0x1F300, 0x1F5FF),
    (0x1F600, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F900, 0x1F9FF),
    (0x1FA70, 0x1FAFF),
    (0x2600, 0x26FF),
    (0x2700, 0x27BF),
]


@cache
def _emoji_table() -> list[tuple[str, str]]:
    table = []
    for start, end in _EMOJI_RANGES:
        for code in range(start, end + 1):
            name = unicodedata.name(chr(code), "")
            if name:
                table.append((chr(code), name.lower()))
    return table


def search_emoji(query: str, limit: int = 40) -> list[tuple[str, str]]:
    """(emoji, name) pairs whose name matches `query`, best first."""
    query = query.strip().lower()
    if not query:
        return []
    scored = []
    for char, name in _emoji_table():
        if name.startswith(query):
            score = 3
        elif _word_starts_with(name, query):
            score = 2
        elif query in name:
            score = 1
        else:
            continue
        scored.append((score, len(name), char, name))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [(char, name) for _, _, char, name in scored[:limit]]
