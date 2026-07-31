from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from html import escape
from typing import Literal

type AspectRatio = Literal["1:1", "4:3", "3:4", "16:9"]
type ImageStyle = Literal["editorial", "product", "concept"]
type ImageJobStatus = Literal["queued", "running", "completed", "canceled"]

QUEUE_DURATION = timedelta(milliseconds=750)
RUN_DURATION = timedelta(milliseconds=2750)


@dataclass(frozen=True, slots=True)
class ImageJobRecord:
    id: str
    prompt: str
    aspect_ratio: AspectRatio
    style: ImageStyle
    seed: int
    created_at: datetime
    canceled_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ImageJobState:
    status: ImageJobStatus
    progress: int
    started_at: datetime | None
    completed_at: datetime | None


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.split())


def resolve_seed(
    prompt: str,
    aspect_ratio: AspectRatio,
    style: ImageStyle,
    seed: int | None,
) -> int:
    if seed is not None:
        return seed
    digest = sha256(f"{prompt}\0{aspect_ratio}\0{style}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def calculate_state(record: ImageJobRecord, now: datetime) -> ImageJobState:
    queued_until = record.created_at + QUEUE_DURATION
    completed_at = queued_until + RUN_DURATION

    if record.canceled_at is not None:
        started_at = queued_until if record.canceled_at >= queued_until else None
        return ImageJobState("canceled", 0, started_at, None)
    if now < queued_until:
        return ImageJobState("queued", 0, None, None)
    if now < completed_at:
        elapsed = (now - queued_until).total_seconds()
        fraction = elapsed / RUN_DURATION.total_seconds()
        return ImageJobState("running", min(95, 8 + round(fraction * 87)), queued_until, None)
    return ImageJobState("completed", 100, queued_until, completed_at)


def image_dimensions(aspect_ratio: AspectRatio) -> tuple[int, int]:
    return {
        "1:1": (1024, 1024),
        "4:3": (1152, 864),
        "3:4": (864, 1152),
        "16:9": (1152, 648),
    }[aspect_ratio]


def render_demo_svg(record: ImageJobRecord) -> str:
    width, height = image_dimensions(record.aspect_ratio)
    source = f"{record.prompt}\0{record.aspect_ratio}\0{record.style}\0{record.seed}"
    digest = sha256(source.encode()).digest()
    palettes = {
        "editorial": ("#142126", "#d8e4dc", "#d16f52", "#7ea29a", "#edf2ee"),
        "product": ("#111923", "#dbe6f5", "#4f83c2", "#d4a84d", "#f3f6fa"),
        "concept": ("#18161d", "#e0d9e6", "#a35d7b", "#6f9285", "#f2eef4"),
    }
    background, paper, accent, secondary, ink = palettes[record.style]
    inset = max(28, width // 24)
    header_height = max(76, height // 9)
    block_width = int(width * (0.46 + (digest[0] / 255) * 0.12))
    horizon = int(height * (0.48 + (digest[1] / 255) * 0.12))
    diagonal = int(width * (0.16 + (digest[2] / 255) * 0.1))
    prompt = escape(normalize_prompt(record.prompt)[:96], quote=True)
    style_label = escape(record.style.upper(), quote=True)

    lines = []
    for index in range(7):
        y = header_height + index * max(28, (height - header_height * 2) // 7)
        opacity = 0.12 + ((digest[3 + index] % 5) * 0.035)
        lines.append(
            f'<line x1="{inset}" y1="{y}" x2="{width - inset}" y2="{y}" '
            f'stroke="{ink}" stroke-opacity="{opacity:.3f}" stroke-width="2" />'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="CanvasRelay demo result">'
        f'<rect width="{width}" height="{height}" fill="{background}" />'
        f'<rect x="{inset}" y="{inset}" width="{width - inset * 2}" height="{height - inset * 2}" '
        f'fill="{paper}" />'
        f'<rect x="{inset}" y="{inset}" width="{width - inset * 2}" height="{header_height}" '
        f'fill="{accent}" />'
        f'<path d="M {inset} {horizon} L {block_width} {header_height + inset} '
        f'L {block_width + diagonal} {height - inset} L {inset} {height - inset} Z" '
        f'fill="{secondary}" />'
        f'<rect x="{block_width + inset}" y="{header_height + inset * 2}" '
        f'width="{max(80, width - block_width - inset * 3)}" '
        f'height="{max(80, horizon - header_height - inset)}" '
        f'fill="{background}" fill-opacity="0.88" />'
        f'{"".join(lines)}'
        f'<rect x="{width - inset * 3}" y="{inset}" width="{inset * 2}" height="{header_height}" '
        f'fill="{ink}" fill-opacity="0.92" />'
        f'<text x="{inset * 1.5}" y="{inset + header_height * 0.6:.0f}" fill="{ink}" '
        f'font-family="Arial, sans-serif" font-size="{max(18, width // 42)}" '
        f'font-weight="700">DEMO RESULT</text>'
        f'<text x="{inset * 1.5}" y="{height - inset * 1.8:.0f}" fill="{background}" '
        f'font-family="Arial, sans-serif" font-size="{max(14, width // 55)}">{prompt}</text>'
        f'<text x="{width - inset * 1.5}" y="{height - inset * 1.8:.0f}" fill="{background}" '
        f'font-family="Arial, sans-serif" font-size="{max(12, width // 68)}" text-anchor="end">'
        f'{style_label} / {record.seed}</text>'
        "</svg>"
    )
