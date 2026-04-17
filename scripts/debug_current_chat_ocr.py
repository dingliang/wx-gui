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
    message_left = window_x + int(width * 0.44)
    message_top = window_y + 68
    message_width = int(width * 0.52)
    message_height = int(height * 0.80)

    recognized = driver._ocr.capture_and_recognize(
        left=message_left,
        top=message_top,
        width=message_width,
        height=message_height,
    )
    chat_title = driver._read_active_chat_title(
        window_x=window_x,
        window_y=window_y,
        width=width,
    )
    is_group_chat = "（" in chat_title or "(" in chat_title
    parsed_messages = driver._read_visible_message_lines(
        window_x=window_x,
        window_y=window_y,
        width=width,
        height=height,
        is_group_chat=is_group_chat,
    )

    print("window_geometry=")
    print(geometry)
    print("chat_title=")
    print(chat_title)
    print("ocr_region=")
    print((message_left, message_top, message_width, message_height))
    print("raw_ocr_candidates=")
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
    print("merged_messages=")
    print(json.dumps(parsed_messages, ensure_ascii=False, indent=2))

    output_dir = Path.cwd() / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / "chat_ocr_debug.png"
    _draw_debug_image(
        driver=driver,
        recognized=recognized,
        message_left=message_left,
        message_top=message_top,
        message_width=message_width,
        message_height=message_height,
        output_path=screenshot_path,
    )
    print(f"debug_image={screenshot_path}")
    return 0


def _draw_debug_image(
    *,
    driver: MacOSAccessibilityDriver,
    recognized: list,
    message_left: int,
    message_top: int,
    message_width: int,
    message_height: int,
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

        rel_left = message_left - window_x
        rel_top = message_top - window_y
        draw.rectangle(
            [rel_left, rel_top, rel_left + message_width, rel_top + message_height],
            outline="blue",
            width=3,
        )

        for item in recognized:
            draw.rectangle(
                [
                    rel_left + item.left,
                    rel_top + item.top,
                    rel_left + item.left + item.width,
                    rel_top + item.top + item.height,
                ],
                outline="green",
                width=2,
            )

        image.save(output_path)
    finally:
        temp_capture.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
