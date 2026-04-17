from __future__ import annotations


class ImageDriver:
    name = "image-fallback"

    def locate(self, template_name: str) -> tuple[int, int] | None:
        # Placeholder for OpenCV-based template matching.
        return None

