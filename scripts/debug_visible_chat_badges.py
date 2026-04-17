from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from app.automation.drivers.accessibility_driver import MacOSAccessibilityDriver
from app.infrastructure.config.settings import load_settings


def main() -> int:
    driver = MacOSAccessibilityDriver(load_settings())
    driver.activate()

    geometry = driver._window_geometry()
    if geometry is None:
        print("Could not read WeChat window geometry.")
        return 1

    window_x, window_y, width, height = geometry
    region_left, region_top, region_width, region_height = driver._visible_chat_list_region(
        window_x=window_x,
        window_y=window_y,
        width=width,
        height=height,
    )
    badge_left, badge_top, badge_width, badge_height = driver._visible_chat_badge_region(
        window_x=window_x,
        window_y=window_y,
        width=width,
        height=height,
    )
    unread_centers = driver._detect_unread_badge_centers(
        left=badge_left,
        top=badge_top,
        width=badge_width,
        height=badge_height,
    )
    recognized = driver._ocr.capture_and_recognize(
        left=region_left,
        top=region_top,
        width=region_width,
        height=region_height,
    )
    entries_unread = driver._read_visible_chat_entries(
        window_x=window_x,
        window_y=window_y,
        width=width,
        height=height,
        unread_only=True,
    )
    entries_all = driver._read_visible_chat_entries(
        window_x=window_x,
        window_y=window_y,
        width=width,
        height=height,
        unread_only=False,
    )
    row_debug = _build_row_debug(
        driver=driver,
        recognized=recognized,
        region_width=region_width,
        region_top=region_top,
        unread_centers=unread_centers,
    )

    print("window_geometry=")
    print(geometry)
    print("chat_list_region=")
    print((region_left, region_top, region_width, region_height))
    print("badge_region=")
    print((badge_left, badge_top, badge_width, badge_height))
    print("unread_centers=")
    print(json.dumps(unread_centers, ensure_ascii=False, indent=2))
    print("recognized=")
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
    print("entries_unread=")
    print(
        json.dumps(
            [{"title": entry.title, "click_x": entry.click_x, "click_y": entry.click_y} for entry in entries_unread],
            ensure_ascii=False,
            indent=2,
        )
    )
    print("entries_all=")
    print(
        json.dumps(
            [{"title": entry.title, "click_x": entry.click_x, "click_y": entry.click_y} for entry in entries_all],
            ensure_ascii=False,
            indent=2,
        )
    )
    print("row_debug=")
    print(json.dumps(row_debug, ensure_ascii=False, indent=2))

    output_dir = Path.cwd() / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / "visible_chat_badges_debug.png"
    badge_capture_path = output_dir / "visible_chat_badges_raw.png"
    _save_badge_capture(
        driver=driver,
        badge_left=badge_left,
        badge_top=badge_top,
        badge_width=badge_width,
        badge_height=badge_height,
        output_path=badge_capture_path,
    )
    _draw_debug_image(
        driver=driver,
        region_left=region_left,
        region_top=region_top,
        region_width=region_width,
        region_height=region_height,
        badge_left=badge_left,
        badge_top=badge_top,
        badge_width=badge_width,
        badge_height=badge_height,
        unread_centers=unread_centers,
        entries_unread=entries_unread,
        row_debug=row_debug,
        output_path=screenshot_path,
    )
    print(f"debug_image={screenshot_path}")
    print(f"badge_debug_image={badge_capture_path}")
    return 0


def _draw_debug_image(
    *,
    driver: MacOSAccessibilityDriver,
    region_left: int,
    region_top: int,
    region_width: int,
    region_height: int,
    badge_left: int,
    badge_top: int,
    badge_width: int,
    badge_height: int,
    unread_centers: list[int],
    entries_unread: list,
    row_debug: list[dict[str, object]],
    output_path: Path,
) -> None:
    geometry = driver._window_geometry()
    if geometry is None:
        return

    window_x, window_y, width, height = geometry
    temp_capture = driver._ocr._capture_region(left=window_x, top=window_y, width=width, height=height)
    try:
        image = Image.open(temp_capture).convert("RGB")
        draw = ImageDraw.Draw(image)

        rel_left = region_left - window_x
        rel_top = region_top - window_y
        draw.rectangle(
            [rel_left, rel_top, rel_left + region_width, rel_top + region_height],
            outline="blue",
            width=3,
        )

        badge_rel_left = badge_left - window_x
        badge_rel_top = badge_top - window_y
        draw.rectangle(
            [badge_rel_left, badge_rel_top, badge_rel_left + badge_width, badge_rel_top + badge_height],
            outline="orange",
            width=3,
        )

        for center in unread_centers:
            y = badge_rel_top + center
            draw.line((badge_rel_left, y, badge_rel_left + badge_width, y), fill="red", width=2)

        for row in row_debug:
            row_top = int(row["row_top"]) - window_y
            row_bottom = int(row["row_bottom"]) - window_y
            color = "lime" if bool(row["matched_unread"]) else "yellow"
            draw.rectangle(
                [rel_left, row_top, rel_left + region_width, row_bottom],
                outline=color,
                width=2,
            )

        for entry in entries_unread:
            x = entry.click_x - window_x
            y = entry.click_y - window_y
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline="green", width=3)

        image.save(output_path)
    finally:
        temp_capture.unlink(missing_ok=True)


def _save_badge_capture(
    *,
    driver: MacOSAccessibilityDriver,
    badge_left: int,
    badge_top: int,
    badge_width: int,
    badge_height: int,
    output_path: Path,
) -> None:
    temp_capture = driver._ocr._capture_region(
        left=badge_left,
        top=badge_top,
        width=badge_width,
        height=badge_height,
    )
    try:
        image = Image.open(temp_capture).convert("RGB")
        image.save(output_path)
    finally:
        temp_capture.unlink(missing_ok=True)


def _build_row_debug(
    *,
    driver: MacOSAccessibilityDriver,
    recognized: list,
    region_width: int,
    region_top: int,
    unread_centers: list[int],
) -> list[dict[str, object]]:
    filtered = [
        item
        for item in recognized
        if item.text.strip()
        and item.confidence >= 0.2
        and item.left < int(region_width * 0.82)
        and not driver._looks_like_time_text(item.text)
        and not driver._looks_like_chat_list_noise(item.text)
    ]
    filtered.sort(key=lambda item: (item.top, item.left))

    lines: list[dict[str, object]] = []
    for item in filtered:
        if not lines:
            lines.append({"top": item.top, "left": item.left, "texts": [item.text.strip()]})
            continue
        current_line = lines[-1]
        if abs(item.top - int(current_line["top"])) <= 20:
            current_line["texts"].append(item.text.strip())
            current_line["left"] = min(int(current_line["left"]), item.left)
        else:
            lines.append({"top": item.top, "left": item.left, "texts": [item.text.strip()]})

    merged_lines: list[tuple[int, int, str]] = []
    for line in lines:
        text = " ".join(line["texts"]).strip()
        if text:
            merged_lines.append((int(line["top"]), int(line["left"]), text))

    rows: list[list[tuple[int, int, str]]] = []
    for line in merged_lines:
        if not rows or line[0] - rows[-1][-1][0] > 34:
            rows.append([line])
        else:
            rows[-1].append(line)

    row_debug: list[dict[str, object]] = []
    for row in rows:
        title_candidates = [
            line for line in row if line[1] < int(region_width * 0.34) and not driver._looks_like_chat_snippet(line[2])
        ]
        if not title_candidates:
            title_candidates = [line for line in row if not driver._looks_like_chat_snippet(line[2])]
        if not title_candidates:
            continue
        title_line = min(title_candidates, key=lambda item: (item[0], item[1]))
        top_values = [line[0] for line in row]
        bottom_values = [line[0] + 24 for line in row]
        row_top = region_top + min(top_values)
        row_bottom = region_top + max(bottom_values)
        matched = [center for center in unread_centers if min(top_values) - 10 <= center <= max(bottom_values) + 10]
        row_debug.append(
            {
                "title": title_line[2],
                "row_top": row_top,
                "row_bottom": row_bottom,
                "matched_unread": bool(matched),
                "matched_centers": matched,
            }
        )
    return row_debug


if __name__ == "__main__":
    raise SystemExit(main())
