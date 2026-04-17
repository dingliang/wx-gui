from __future__ import annotations

import json
import sys
from pathlib import Path

from ApplicationServices import (
    kAXPositionAttribute,
    kAXRoleAttribute,
    kAXSizeAttribute,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)
from PIL import Image, ImageDraw

from app.automation.drivers.accessibility_driver import MacOSAccessibilityDriver
from app.infrastructure.config.settings import load_settings


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/debug_wechat_search.py <target>")
        return 1

    target = sys.argv[1].strip()
    if not target:
        print("Target must not be empty.")
        return 1

    driver = MacOSAccessibilityDriver(load_settings())
    driver.activate()
    driver._open_search()
    driver._clear_active_input()
    driver._paste_text(target)
    driver._delay(0.6)

    geometry = driver._window_geometry()
    if geometry is None:
        print("Could not read WeChat window geometry.")
        return 2

    window_x, window_y, width, height = geometry
    left_pane_max_x = window_x + int(width * 0.42)
    search_area_top_y = window_y + 56
    search_area_bottom_y = window_y + int(height * 0.72)

    matches = driver._find_matching_elements(
        target=target,
        left_pane_max_x=left_pane_max_x,
        search_area_top_y=search_area_top_y,
        search_area_bottom_y=search_area_bottom_y,
    )

    print("window_geometry=", geometry)
    print("matched_candidates=")
    print(
        json.dumps(
            [
                {
                    "text": item.text,
                    "center_x": item.center_x,
                    "center_y": item.center_y,
                    "score": item.score,
                }
                for item in matches
            ],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("ocr_candidates=")
    result_left, result_top, result_width, result_height = driver._search_result_region(
        window_x=window_x,
        window_y=window_y,
        width=width,
        height=height,
    )
    debug_info = driver.debug_search_target_with_ocr(target=target)
    recognized = debug_info["ocr_candidates"]
    print(
        json.dumps(
            [
                {
                    "text": item.text,
                    "confidence": item.confidence,
                    "left": item.left,
                    "top": item.top,
                    "width": item.width,
                    "height": item.height,
                }
                for item in recognized
            ],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("click_target=")
    click_target = debug_info["click_target"]
    if click_target is None:
        print("null")
    else:
        print(
            json.dumps(
                {
                    "text": click_target.text,
                    "click_x": click_target.click_x,
                    "click_y": click_target.click_y,
                    "score": click_target.score,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    debug_image_path = Path.cwd() / "data" / "ocr_debug.png"
    _draw_debug_image(
        driver=driver,
        recognized=recognized,
        click_target=click_target,
        output_path=debug_image_path,
    )
    print(f"debug_image={debug_image_path}")

    print("tree_excerpt=")
    process = driver._application_element()
    if process is None:
        print("[]")
        return 0

    excerpt: list[dict[str, object]] = []
    for node in driver._iter_accessibility_tree(process):
        if node.depth > 8:
            continue

        element = node.element
        texts = driver._element_texts(element)
        if not texts:
            continue

        position = driver._ax_point(element, kAXPositionAttribute, kAXValueCGPointType) or node.inherited_position
        size = driver._ax_size(element, kAXSizeAttribute, kAXValueCGSizeType) or node.inherited_size
        role = driver._ax_string(element, kAXRoleAttribute)

        center_x = None
        center_y = None
        if position is not None and size is not None:
            center_x = int(position.x + (size.width / 2))
            center_y = int(position.y + (size.height / 2))

        if center_x is not None and center_x > left_pane_max_x:
            continue
        if center_y is not None and (center_y < search_area_top_y or center_y > search_area_bottom_y):
            continue

        excerpt.append(
            {
                "depth": node.depth,
                "role": role,
                "texts": texts[:5],
                "center_x": center_x,
                "center_y": center_y,
            }
        )

        if len(excerpt) >= 80:
            break

    print(json.dumps(excerpt, ensure_ascii=False, indent=2))
    return 0


def _draw_debug_image(
    *,
    driver: MacOSAccessibilityDriver,
    recognized: list,
    click_target,
    output_path: Path,
) -> None:
    geometry = driver._window_geometry()
    if geometry is None:
        return

    window_x, window_y, width, height = geometry
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_capture = driver._ocr._capture_region(left=window_x, top=window_y, width=width, height=height)
    try:
        image = Image.open(temp_capture).convert("RGB")
        draw = ImageDraw.Draw(image)

        _, _, result_width, result_height = driver._search_result_region(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )
        result_left = int(width * 0.06)
        result_top = 52
        draw.rectangle(
            [result_left, result_top, result_left + result_width, result_top + result_height],
            outline="blue",
            width=2,
        )

        for item in recognized:
            draw.rectangle(
                [
                    result_left + item.left,
                    result_top + item.top,
                    result_left + item.left + item.width,
                    result_top + item.top + item.height,
                ],
                outline="green",
                width=2,
            )

        if click_target is not None:
            cx = click_target.click_x - window_x
            cy = click_target.click_y - window_y
            draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline="red", width=3)
            draw.line([cx - 12, cy, cx + 12, cy], fill="red", width=3)
            draw.line([cx, cy - 12, cx, cy + 12], fill="red", width=3)

        image.save(output_path)
    finally:
        temp_capture.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
