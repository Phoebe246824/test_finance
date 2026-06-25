#!/usr/bin/env python3
"""
Export HTML slides to PNG images, then assemble into a PPTX file.

Requires: playwright, python-pptx, pillow
  uv pip install playwright python-pptx pillow
  playwright install chromium

Usage:
  python scripts/export_slides_to_pptx.py --index-dir output/slides/competition-demo
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export HTML slides → PNG images → PPTX file"
    )
    parser.add_argument(
        "--index-dir",
        type=str,
        required=True,
        help="Directory containing index.html (e.g. output/slides/competition-demo). "
        "No default — must be specified.",
    )
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=1920,
        help="Viewport width for rendering (default: 1920)",
    )
    parser.add_argument(
        "--viewport-height",
        type=int,
        default=1080,
        help="Viewport height for rendering (default: 1080)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for PNGs and PPTX. Defaults to <index-dir>/dist.",
    )
    parser.add_argument(
        "--pptx-name",
        type=str,
        default=None,
        help="PPTX filename (without path). Defaults to <dirname>-rendered.pptx.",
    )
    return parser.parse_args()


async def export_slides(
    index_html: Path,
    dist_dir: Path,
    viewport_width: int,
    viewport_height: int,
    pptx_name: str,
) -> None:
    """Render HTML slides as PNG images, then assemble into PPTX."""
    from playwright.async_api import async_playwright

    dist_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Launch headless Chromium with no sandbox for CI/docker compatibility
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=2,  # 2x for sharper output
        )
        page = await context.new_page()

        # Navigate using file:// URL
        await page.goto(index_html.as_uri(), wait_until="networkidle")

        # Override the presentation JS to show all slides at once:
        # 1. Remove the stage transform (so 1920×1080 canvas fills viewport)
        # 2. Make ALL slides visible + positioned sequentially
        await page.evaluate("""
            () => {
                // Disable stage scaling — render at native 1920×1080
                const stage = document.getElementById("deckStage");
                if (stage) {
                    stage.style.transform = "none";
                    stage.style.position = "relative";
                    stage.style.overflow = "visible";
                    stage.style.height = "auto";
                }

                // Make all slides visible and stack them
                const slides = document.querySelectorAll(".slide");
                let accumulatedTop = 0;
                slides.forEach((slide, i) => {
                    slide.style.visibility = "visible";
                    slide.style.opacity = "1";
                    slide.style.pointerEvents = "auto";
                    slide.style.position = "relative";
                    slide.style.zIndex = String(i + 1);
                    slide.style.top = accumulatedTop + "px";
                    accumulatedTop += 1080;
                });

                // Hide controls
                const controls = document.querySelector(".deck-controls");
                if (controls) controls.style.display = "none";
                const hotzone = document.querySelector(".edit-hotzone");
                if (hotzone) hotzone.style.display = "none";
                const editToggle = document.getElementById("editToggle");
                if (editToggle) editToggle.style.display = "none";
                const saveToast = document.getElementById("saveToast");
                if (saveToast) saveToast.style.display = "none";

                // Expand body to fit all slides
                document.body.style.overflow = "visible";
                document.body.style.height = "auto";
                document.documentElement.style.overflow = "visible";
                document.documentElement.style.height = "auto";
            }
        """)

        # Wait for reveal animations to complete
        await page.wait_for_timeout(1000)

        # Screenshot each slide individually
        slides = await page.query_selector_all(".slide")
        slide_count = len(slides)

        if slide_count == 0:
            print("ERROR: No .slide elements found in the HTML.", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        print(f"Found {slide_count} slides. Exporting PNGs to {dist_dir} ...")

        image_paths: list[Path] = []
        for i, slide in enumerate(slides):
            slide_num = str(i + 1).zfill(2)
            filename = f"slide-{slide_num}.png"
            filepath = dist_dir / filename

            # Scroll the slide into view before screenshot
            await slide.scroll_into_view_if_needed()
            await page.wait_for_timeout(200)

            # Take element screenshot at the slide's rendered size (1920×1080)
            await slide.screenshot(path=str(filepath), type="png")
            image_paths.append(filepath)
            print(f"  ✓ {filename}")

        await browser.close()

    # --- Assemble PPTX ---
    print(f"\nAssembling PPTX from {len(image_paths)} images ...")
    _assemble_pptx(image_paths, dist_dir / pptx_name, viewport_width, viewport_height)
    print(f"  ✓ {pptx_name}")

    # --- Write manifest ---
    manifest = {
        "slide_count": slide_count,
        "images": [str(p.resolve()) for p in image_paths],
        "pptx": str((dist_dir / pptx_name).resolve()),
    }
    manifest_path = dist_dir / "export-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nManifest written to {manifest_path}")

    # Cleanup: remove individual PNGs to keep dist tidy?
    # Keep them by default — user may want them. Remove if requested.
    print(f"\nDone: {slide_count} slides → {len(image_paths)} PNGs → {pptx_name}")


def _assemble_pptx(
    image_paths: list[Path],
    pptx_path: Path,
    width_px: int,
    height_px: int,
) -> None:
    """Create a PPTX with one full-slide image per page."""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Emu
    except ImportError:
        print(
            "ERROR: python-pptx is not installed. Run: uv pip install python-pptx",
            file=sys.stderr,
        )
        sys.exit(1)

    # Convert pixels to EMU (English Metric Units).
    # 1 inch = 914400 EMU, and playright renders at screen PPI.
    # For a 16:9 presentation at standard 96 DPI, 1920×1080 → 20" × 11.25"
    # But we use the actual dimensions: map pixels directly to slide dimensions.
    # Standard PPTX slide: 13.333" × 7.5" for 16:9 (widescreen).
    # We map viewport pixels to these inches.
    px_per_inch = 96  # Playwright default
    slide_width_in = width_px / px_per_inch  # e.g. 1920/96 = 20"
    slide_height_in = height_px / px_per_inch  # e.g. 1080/96 = 11.25"

    prs = Presentation()
    prs.slide_width = Inches(slide_width_in)
    prs.slide_height = Inches(slide_height_in)

    # Use blank layout
    blank_layout = prs.slide_layouts[6]  # blank

    for img_path in image_paths:
        slide = prs.slides.add_slide(blank_layout)
        # Add image filling the entire slide
        slide.shapes.add_picture(
            str(img_path),
            left=0,
            top=0,
            width=prs.slide_width,
            height=prs.slide_height,
        )

    prs.save(str(pptx_path))


def main() -> None:
    args = parse_args()

    index_dir = Path(args.index_dir).resolve()
    if not index_dir.is_dir():
        print(f"ERROR: --index-dir '{index_dir}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    index_html = index_dir / "index.html"
    if not index_html.is_file():
        print(f"ERROR: index.html not found in '{index_dir}'.", file=sys.stderr)
        sys.exit(1)

    dist_dir = Path(args.output_dir).resolve() if args.output_dir else (index_dir / "dist")
    pptx_name = args.pptx_name or f"{index_dir.name}-rendered.pptx"

    print(f"Index HTML:   {index_html}")
    print(f"Output dir:   {dist_dir}")
    print(f"Viewport:     {args.viewport_width}×{args.viewport_height}")
    print(f"PPTX:         {pptx_name}")
    print()

    asyncio.run(
        export_slides(
            index_html=index_html,
            dist_dir=dist_dir,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            pptx_name=pptx_name,
        )
    )


if __name__ == "__main__":
    main()