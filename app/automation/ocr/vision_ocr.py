from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from AppKit import NSScreen
from Foundation import NSURL
from PIL import Image, ImageFilter, ImageOps
import Vision

from app.automation.exceptions import DriverError


@dataclass
class OCRTextBox:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int

    @property
    def center_x(self) -> int:
        return self.left + (self.width // 2)

    @property
    def center_y(self) -> int:
        return self.top + (self.height // 2)


class VisionOCRService:
    def capture_and_recognize(
        self,
        *,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> list[OCRTextBox]:
        screenshot_path = self._capture_region(left=left, top=top, width=width, height=height)
        prepared_path: Path | None = None
        try:
            prepared_path = self._prepare_image(screenshot_path)
            recognized = self._recognize_prepared_image(prepared_path)
            prepared_image = Image.open(prepared_path)
            captured_width, captured_height = prepared_image.size
            if captured_width <= 0 or captured_height <= 0:
                return recognized

            scale_x = width / captured_width
            scale_y = height / captured_height

            return [
                OCRTextBox(
                    text=item.text,
                    confidence=item.confidence,
                    left=int(item.left * scale_x),
                    top=int(item.top * scale_y),
                    width=max(int(item.width * scale_x), 1),
                    height=max(int(item.height * scale_y), 1),
                )
                for item in recognized
            ]
        finally:
            if prepared_path is not None:
                prepared_path.unlink(missing_ok=True)
            screenshot_path.unlink(missing_ok=True)

    def recognize_image(self, image_path: Path) -> list[OCRTextBox]:
        prepared_path = self._prepare_image(image_path)
        try:
            return self._recognize_prepared_image(prepared_path)
        finally:
            if prepared_path != image_path:
                prepared_path.unlink(missing_ok=True)

    def _capture_region(self, *, left: int, top: int, width: int, height: int) -> Path:
        fd, path_str = tempfile.mkstemp(suffix=".png", prefix="wx-gui-search-")
        Path(path_str).unlink(missing_ok=True)

        safe_left, safe_top, safe_width, safe_height = self._clamp_region(
            left=left,
            top=top,
            width=width,
            height=height,
        )
        region = f"{safe_left},{safe_top},{safe_width},{safe_height}"
        completed = subprocess.run(
            ["screencapture", "-x", "-R", region, path_str],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise DriverError(completed.stderr.strip() or "Failed to capture the search result area.")
        return Path(path_str)

    def _clamp_region(self, *, left: int, top: int, width: int, height: int) -> tuple[int, int, int, int]:
        desktop_left, desktop_top, desktop_width, desktop_height = self._desktop_bounds()
        desktop_right = desktop_left + desktop_width
        desktop_bottom = desktop_top + desktop_height

        clamped_left = min(max(left, desktop_left), desktop_right - 1)
        clamped_top = min(max(top, desktop_top), desktop_bottom - 1)
        requested_right = left + max(width, 1)
        requested_bottom = top + max(height, 1)
        clamped_right = min(max(requested_right, clamped_left + 1), desktop_right)
        clamped_bottom = min(max(requested_bottom, clamped_top + 1), desktop_bottom)

        return (
            int(clamped_left),
            int(clamped_top),
            max(int(clamped_right - clamped_left), 1),
            max(int(clamped_bottom - clamped_top), 1),
        )

    def _desktop_bounds(self) -> tuple[int, int, int, int]:
        screens = NSScreen.screens() or []
        if not screens:
            return (0, 0, 1440, 900)

        min_x: float | None = None
        min_y: float | None = None
        max_x: float | None = None
        max_y: float | None = None

        for screen in screens:
            frame = screen.frame()
            screen_min_x = float(frame.origin.x)
            screen_min_y = float(frame.origin.y)
            screen_max_x = screen_min_x + float(frame.size.width)
            screen_max_y = screen_min_y + float(frame.size.height)

            min_x = screen_min_x if min_x is None else min(min_x, screen_min_x)
            min_y = screen_min_y if min_y is None else min(min_y, screen_min_y)
            max_x = screen_max_x if max_x is None else max(max_x, screen_max_x)
            max_y = screen_max_y if max_y is None else max(max_y, screen_max_y)

        assert min_x is not None and min_y is not None and max_x is not None and max_y is not None
        return (int(min_x), int(min_y), max(int(max_x - min_x), 1), max(int(max_y - min_y), 1))

    def _prepare_image(self, image_path: Path) -> Path:
        image = Image.open(image_path)
        processed = image.convert("L")
        processed = ImageOps.autocontrast(processed)
        processed = processed.filter(ImageFilter.SHARPEN)
        processed = processed.resize((processed.width * 3, processed.height * 3))

        fd, prepared_path_str = tempfile.mkstemp(suffix=".png", prefix="wx-gui-ocr-")
        Path(prepared_path_str).unlink(missing_ok=True)
        prepared_path = Path(prepared_path_str)
        processed.save(prepared_path)
        return prepared_path

    def _recognize_prepared_image(self, image_path: Path) -> list[OCRTextBox]:
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(False)
        request.setRecognitionLanguages_(["zh-Hans", "en-US"])

        image_url = NSURL.fileURLWithPath_(str(image_path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(image_url, None)
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise DriverError(str(error) if error else "Vision OCR request failed.")

        image = Image.open(image_path)
        image_width, image_height = image.size

        results: list[OCRTextBox] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue

            candidate = candidates[0]
            text = candidate.string().strip()
            if not text:
                continue

            bbox = observation.boundingBox()
            left = int(bbox.origin.x * image_width)
            width = int(bbox.size.width * image_width)
            height = int(bbox.size.height * image_height)
            top = int((1 - bbox.origin.y - bbox.size.height) * image_height)

            results.append(
                OCRTextBox(
                    text=text,
                    confidence=float(candidate.confidence()),
                    left=left,
                    top=top,
                    width=max(width, 1),
                    height=max(height, 1),
                )
            )

        return results
