"""Deterministic generator for splunkgate_app's Splunk icon set + Splunkbase screenshot.

Renders 5 PNGs via Pillow:
- appIcon.png         (36x36)  dark navy + Splunk-blue shield
- appIcon_2x.png      (72x72)  hi-DPI variant
- appIconAlt.png      (36x36)  light surface + Splunk-blue shield
- appIconAlt_2x.png   (72x72)  hi-DPI variant of alt
- screenshot.png      (1280x720) Splunkbase listing placeholder

Determinism contract: PIL output is byte-identical given identical input.
This script intentionally takes no random/time inputs. CI re-runs and asserts
md5 equality against the committed PNGs (story-app-09 shell block 4).

Brand tokens (must match docs/ux-spec.md § "Design tokens"):
- NAVY    #1A1C20  dark background
- LIGHT   #F8F9FA  alt-icon background
- BLUE    #1A8FFF  primary action / shield fill

Glyph: an SplunkGate is a shield in Greek mythology — apt for an agent safety
shield. The glyph is a shield outline + an inner notch, simple enough to
render legibly at 36x36.

Usage:
    python scripts/generate_app_icons.py [--output-dir DIR]

Default output dir is splunk_apps/splunkgate_app/static/. CI invokes with a
tmp dir to verify md5 determinism.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NAVY = "#1A1C20"
LIGHT = "#F8F9FA"
BLUE = "#1A8FFF"

# Splunkbase listing placeholder gets the brand wordmark + tagline.
WORDMARK = "SPLUNKGATE"
TAGLINE = "Real-time AI agent safety verdicts"

# Pillow's bundled bitmap font: identical bytes across every install of the
# same Pillow version, on every OS. Picking it kills the Mac-Arial vs
# Ubuntu-DejaVu drift that would otherwise silently break BDD block 4 the
# moment CI regenerates on a Linux runner. Pillow is pinned exact in
# pyproject.toml so a future minor bump can't shift glyph metrics either.
TITLE_PX = 120
TAGLINE_PX = 36


def _draw_shield(canvas: Image.Image, size: int, fg: str) -> None:
    """Draw a centered shield glyph on `canvas` of `size x size`.

    Shield geometry is parameterized off `size` so 36x36 and 72x72 stay
    visually identical at different DPIs. No anti-alias kludges — Pillow's
    polygon renderer handles small sizes acceptably for app launcher use.
    """
    draw = ImageDraw.Draw(canvas)
    margin = size // 6
    top = margin
    bottom = size - margin
    left = margin
    right = size - margin
    mid_x = size // 2
    # Shoulder Y is 1/3 down the shield body — gives the classic "shield" silhouette.
    shoulder_y = top + (bottom - top) // 3
    points = [
        (left, top),
        (right, top),
        (right, shoulder_y),
        (mid_x, bottom),
        (left, shoulder_y),
    ]
    draw.polygon(points, fill=fg)
    # Inner notch (a small inverted triangle at the top center) lifts
    # the shape away from a plain pentagon and reads as "shield" not "house".
    notch_w = size // 8
    notch_h = size // 6
    notch = [
        (mid_x - notch_w, top),
        (mid_x + notch_w, top),
        (mid_x, top + notch_h),
    ]
    bg = canvas.getpixel((1, 1))
    draw.polygon(notch, fill=bg)


def _make_icon(size: int, bg: str) -> Image.Image:
    """Return an icon `size x size` with `bg` background + blue shield glyph."""
    canvas = Image.new("RGB", (size, size), bg)
    _draw_shield(canvas, size, BLUE)
    return canvas


def _make_screenshot(width: int = 1280, height: int = 720) -> Image.Image:
    """Splunkbase listing placeholder: wordmark + tagline on dark background.

    story-app-12 swaps this for a real dashboard screenshot before submission.
    """
    canvas = Image.new("RGB", (width, height), NAVY)
    draw = ImageDraw.Draw(canvas)
    title_font = ImageFont.load_default(size=TITLE_PX)
    tagline_font = ImageFont.load_default(size=TAGLINE_PX)
    tb = draw.textbbox((0, 0), WORDMARK, font=title_font)
    title_w, title_h = tb[2] - tb[0], tb[3] - tb[1]
    draw.text(
        ((width - title_w) // 2, (height - title_h) // 2 - 40),
        WORDMARK,
        fill=BLUE,
        font=title_font,
    )
    sb = draw.textbbox((0, 0), TAGLINE, font=tagline_font)
    sub_w = sb[2] - sb[0]
    draw.text(
        ((width - sub_w) // 2, (height + title_h) // 2 + 10),
        TAGLINE,
        fill=LIGHT,
        font=tagline_font,
    )
    return canvas


def generate_all(output_dir: Path) -> None:
    """Write all 5 PNGs into `output_dir`. Creates dir if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("appIcon.png", 36, NAVY),
        ("appIcon_2x.png", 72, NAVY),
        ("appIconAlt.png", 36, LIGHT),
        ("appIconAlt_2x.png", 72, LIGHT),
    ]
    for name, size, bg in specs:
        img = _make_icon(size, bg)
        img.save(output_dir / name, format="PNG", optimize=True)
    _make_screenshot().save(output_dir / "screenshot.png", format="PNG", optimize=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate splunkgate_app icon set.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("splunk_apps/splunkgate_app/static"),
        help="Directory to write the 5 PNGs into.",
    )
    args = parser.parse_args(argv)
    generate_all(args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
