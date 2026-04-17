from __future__ import annotations

from difflib import SequenceMatcher
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from PIL import Image

from app.automation.drivers.applescript_driver import AppleScriptDriver
from app.automation.ocr.vision_ocr import OCRTextBox, VisionOCRService
from app.automation.exceptions import (
    AccessibilityPermissionError,
    DriverError,
    LoginRequiredError,
    TargetNotFoundError,
    WindowNotFoundError,
)
from app.infrastructure.config.settings import AppSettings

from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXValueGetValue,
    kAXChildrenAttribute,
    kAXDescriptionAttribute,
    kAXFocusedWindowAttribute,
    kAXPositionAttribute,
    kAXRoleAttribute,
    kAXSizeAttribute,
    kAXTitleAttribute,
    kAXValueAttribute,
    kAXValueCGPointType,
    kAXValueCGSizeType,
    kAXWindowsAttribute,
)


@dataclass
class _AXMatchCandidate:
    text: str
    center_x: int
    center_y: int
    score: int


@dataclass
class _OCRClickTarget:
    text: str
    click_x: int
    click_y: int
    score: float


@dataclass
class _AXTraversalNode:
    element: Any
    depth: int
    inherited_position: Any | None
    inherited_size: Any | None


@dataclass
class _VisibleChatEntry:
    title: str
    click_x: int
    click_y: int


class MacOSAccessibilityDriver:
    name = "macos-accessibility"
    _TIME_PATTERN = re.compile(
        r"^(?:\d{1,2}:\d{2}|昨天\s*\d{1,2}:\d{2}|今天\s*\d{1,2}:\d{2}|"
        r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)$"
    )

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._applescript = AppleScriptDriver()
        self._ocr = VisionOCRService()
        self._last_error = ""
        self._app_names = self._build_app_names()

    def is_running(self) -> bool:
        for app_name in self._app_names:
            script = f'tell application "System Events" to (name of processes) contains "{app_name}"'
            if self._safe_bool_script(script):
                return True
        return False

    def is_logged_in(self) -> bool:
        if not self.is_running():
            return False

        windows = self._window_names()
        if not windows:
            return False

        joined = " ".join(windows).lower()
        login_markers = ["login", "sign in", "scan", "qr", "登录", "扫码"]
        return not any(marker in joined for marker in login_markers)

    def activate(self) -> None:
        completed = subprocess.run(
            ["open", "-a", self._resolve_app_name()],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise DriverError(completed.stderr.strip() or "Failed to activate WeChat.")
        self._applescript.run(
            (
                'tell application "System Events"\n'
                f'  tell process "{self._resolve_process_name()}"\n'
                "    set frontmost to true\n"
                "  end tell\n"
                "end tell"
            )
        )

    def search_chat(self, keyword: str) -> bool:
        self._ensure_ready()
        normalized_keyword = self._searchable_chat_name(keyword)
        if not normalized_keyword:
            return False

        for _ in range(2):
            self.activate()
            self._open_search()
            self._clear_active_input()
            self._paste_text(normalized_keyword)
            self._delay(0.45)
            if self._select_search_result(normalized_keyword):
                self._delay(0.35)
                return True
            self._delay(0.2)

        return False

    def open_chat(self, name: str) -> None:
        searchable_name = self._searchable_chat_name(name)
        opened = self.search_chat(searchable_name)
        if not opened:
            raise TargetNotFoundError(f'Could not find an exact search result for "{searchable_name}".')
        if not self._wait_for_active_chat(searchable_name):
            raise TargetNotFoundError(
                f'Opened chat title does not match target "{searchable_name}". Message sending was stopped for safety.'
            )

    def send_text(self, text: str) -> None:
        self._ensure_ready()
        self.activate()
        self._focus_message_input()
        self._paste_text(text)
        self._delay(0.2)
        self._press_enter()

    def send_file(self, file_path: str) -> None:
        raise NotImplementedError("send_file is not implemented yet.")

    def read_current_chat_messages(self) -> dict[str, object]:
        self._ensure_ready()
        geometry = self._window_geometry()
        if geometry is None:
            raise DriverError("Could not read WeChat window geometry.")

        window_x, window_y, width, height = geometry
        title = self._read_active_chat_title(window_x=window_x, window_y=window_y, width=width)
        is_group_chat = bool(re.search(r"[（(]\d+[）)]", title))
        messages = self._read_visible_message_lines(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
            is_group_chat=is_group_chat,
        )
        return {
            "chat_title": title,
            "messages": messages,
        }

    def read_visible_chat_snapshots(self, unread_only: bool = False) -> dict[str, object]:
        self._ensure_ready()
        geometry = self._window_geometry()
        if geometry is None:
            raise DriverError("Could not read WeChat window geometry.")

        window_x, window_y, width, height = geometry
        original_title = self._read_active_chat_title(window_x=window_x, window_y=window_y, width=width)
        entries = self._read_visible_chat_entries(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
            unread_only=unread_only,
        )
        if not entries:
            return {"chats": []}

        self.activate()
        snapshots: list[dict[str, object]] = []
        seen_titles: set[str] = set()
        current_title = original_title

        for entry in entries:
            if entry.title in seen_titles:
                continue

            opened = self._open_visible_chat_entry(entry)
            payload = self._read_current_chat_messages_with_retry(expected_title=entry.title)
            chat_title = str(payload.get("chat_title", "")).strip() or entry.title
            messages = payload.get("messages", [])
            if not isinstance(messages, list):
                messages = []

            if not opened:
                normalized_expected = self._normalize_chat_name(entry.title)
                normalized_title = self._normalize_chat_name(chat_title)
                if normalized_expected != normalized_title and not messages:
                    continue

            seen_titles.add(chat_title)
            snapshots.append(
                {
                    "chat_title": chat_title,
                    "messages": messages,
                }
            )
            current_title = chat_title

        if original_title and current_title != original_title:
            original_entry = next(
                (
                    entry
                    for entry in entries
                    if self._normalize_chat_name(entry.title) == self._normalize_chat_name(original_title)
                ),
                None,
            )
            if original_entry is not None:
                self._open_visible_chat_entry(original_entry)

        return {"chats": snapshots}

    def _open_visible_chat_entry(self, entry: _VisibleChatEntry) -> bool:
        self._click_point(entry.click_x, entry.click_y)
        self._delay(0.35)
        if not self._wait_for_active_chat(entry.title):
            return False
        self._delay(0.25)
        return True

    def _read_current_chat_messages_with_retry(self, *, expected_title: str) -> dict[str, object]:
        last_payload: dict[str, object] = {"chat_title": expected_title, "messages": []}
        for delay_seconds in (0.0, 0.45, 0.8):
            if delay_seconds > 0:
                self._delay(delay_seconds)

            payload = self.read_current_chat_messages()
            chat_title = str(payload.get("chat_title", "")).strip()
            messages = payload.get("messages", [])
            if not isinstance(messages, list):
                messages = []
                payload["messages"] = messages

            last_payload = payload
            if messages:
                return payload

            # After we have successfully switched to the expected chat, give the
            # message area additional time to render before giving up.
            if chat_title and self._normalize_chat_name(chat_title) != self._normalize_chat_name(expected_title):
                continue

        return last_payload

    def capture_state(self) -> dict[str, str]:
        return {
            "driver": self.name,
            "platform": self._settings.platform_name,
            "wechat_app_name": self._resolve_process_name(),
            "last_error": self._last_error,
        }

    def _window_names(self) -> list[str]:
        script = (
            'tell application "System Events"\n'
            f'  tell process "{self._resolve_process_name()}"\n'
            "    get name of every window\n"
            "  end tell\n"
            "end tell"
        )
        output = self._applescript.run(script)
        if not output:
            return []
        return [name.strip() for name in output.split(",") if name.strip()]

    def _ensure_ready(self) -> None:
        if not self.is_running():
            raise WindowNotFoundError("WeChat is not running.")
        if not self.is_logged_in():
            raise LoginRequiredError(
                "WeChat appears to be open but not logged in, or automation permissions are not available yet."
            )

    def _safe_bool_script(self, script: str) -> bool:
        try:
            self._last_error = ""
            return self._applescript.run(script).strip().lower() == "true"
        except AccessibilityPermissionError as exc:
            self._last_error = str(exc)
            return False

    def _build_app_names(self) -> list[str]:
        candidates = [self._settings.wechat_app_name, "WeChat", "微信"]
        unique: list[str] = []
        for name in candidates:
            if name and name not in unique:
                unique.append(name)
        return unique

    def _resolve_app_name(self) -> str:
        for app_name in self._app_names:
            completed = subprocess.run(
                ["open", "-Ra", app_name],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                return app_name
        return self._app_names[0]

    def _resolve_process_name(self) -> str:
        for app_name in self._app_names:
            script = f'tell application "System Events" to (name of processes) contains "{app_name}"'
            if self._safe_bool_script(script):
                return app_name
        return self._resolve_app_name()

    def _send_keystroke(self, key: str, using: str | None = None) -> None:
        if using:
            script = (
                'tell application "System Events"\n'
                f'  keystroke "{key}" using {using}\n'
                "end tell"
            )
        else:
            script = (
                'tell application "System Events"\n'
                f'  keystroke "{key}"\n'
                "end tell"
        )
        self._applescript.run(script)

    def _open_search(self) -> None:
        self._send_keystroke("f", using="{command down}")
        self._delay(0.25)

    def _clear_active_input(self) -> None:
        self._send_keystroke("a", using="{command down}")
        self._delay(0.08)
        self._press_key_code(51)  # Delete
        self._delay(0.1)

    def _press_enter(self) -> None:
        self._press_key_code(36)

    def _press_key_code(self, key_code: int) -> None:
        script = (
            'tell application "System Events"\n'
            f"  key code {key_code}\n"
            "end tell"
        )
        self._applescript.run(script)

    def _delay(self, seconds: float) -> None:
        self._applescript.run(f"delay {seconds}", timeout=max(5.0, seconds + 2.0))

    def _select_search_result(self, target: str) -> bool:
        geometry = self._window_geometry()
        if geometry is None:
            return False

        window_x, window_y, width, height = geometry
        left_pane_max_x = window_x + int(width * 0.42)
        search_area_top_y = window_y + 56
        search_area_bottom_y = window_y + int(height * 0.72)

        matches = self._find_matching_elements(
            target=target,
            left_pane_max_x=left_pane_max_x,
            search_area_top_y=search_area_top_y,
            search_area_bottom_y=search_area_bottom_y,
        )
        if matches:
            best_match = max(matches, key=lambda item: item.score)
            self._click_point(best_match.center_x, best_match.center_y)
            return True

        ocr_match = self._select_search_result_with_ocr(
            target=target,
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )
        if ocr_match is None:
            return False

        self._click_point(ocr_match.click_x, ocr_match.click_y)
        return True

    def _focus_message_input(self) -> None:
        geometry = self._window_geometry()
        if geometry is None:
            return

        x, y, width, height = geometry
        click_x = x + (width // 2)
        click_y = y + max(int(height * 0.82), height - 120)

        try:
            self._click_point(click_x, click_y)
        except DriverError:
            raise
        self._delay(0.1)

    def _paste_text(self, text: str) -> None:
        completed = subprocess.run(
            ["pbcopy"],
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise DriverError(completed.stderr.strip() or "Failed to copy text to clipboard.")

        script = (
            'tell application "System Events"\n'
            '  keystroke "v" using {command down}\n'
            "end tell"
        )
        self._applescript.run(script)

    def _window_geometry(self) -> tuple[int, int, int, int] | None:
        focused_window = self._focused_window()
        if focused_window is None:
            return self._window_geometry_via_script()

        position = self._ax_point(focused_window, kAXPositionAttribute, kAXValueCGPointType)
        size = self._ax_size(focused_window, kAXSizeAttribute, kAXValueCGSizeType)
        if position and size:
            return (int(position.x), int(position.y), int(size.width), int(size.height))

        return self._window_geometry_via_script()

    def _window_geometry_via_script(self) -> tuple[int, int, int, int] | None:
        script = (
            'tell application "System Events"\n'
            f'  tell process "{self._resolve_process_name()}"\n'
            "    if (count of windows) is 0 then return \"\"\n"
            "    set windowPosition to position of window 1\n"
            "    set windowSize to size of window 1\n"
            "    return (item 1 of windowPosition as text) & \",\" & (item 2 of windowPosition as text) & \",\" & "
            '           (item 1 of windowSize as text) & "," & (item 2 of windowSize as text)\n'
            "  end tell\n"
            "end tell"
        )
        output = self._applescript.run(script)
        if not output:
            return None

        parts = [part.strip() for part in output.split(",")]
        if len(parts) != 4:
            return None

        try:
            return cast(tuple[int, int, int, int], tuple(int(part) for part in parts))
        except ValueError:
            return None

    def _select_search_result_with_ocr(
        self,
        *,
        target: str,
        window_x: int,
        window_y: int,
        width: int,
        height: int,
    ) -> _OCRClickTarget | None:
        result_left, result_top, result_width, result_height = self._search_result_region(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )
        if result_width <= 0 or result_height <= 0:
            return None

        recognized = self._ocr.capture_and_recognize(
            left=result_left,
            top=result_top,
            width=result_width,
            height=result_height,
        )
        if not recognized:
            return None

        normalized_target = self._normalize_chat_name(target)
        best_match: _OCRClickTarget | None = None
        best_score = 0.0
        row_click_x = window_x + int(width * 0.22)

        for item in recognized:
            normalized_text = self._normalize_chat_name(item.text)
            if not normalized_text:
                continue

            if self._is_ocr_noise_text(normalized_text):
                continue

            score = 0.0
            if normalized_text == normalized_target:
                score += 100
            elif normalized_target in normalized_text:
                score += 50
            elif self._chat_match_similarity(
                normalized_target=normalized_target,
                normalized_text=normalized_text,
            ) >= self._settings.chat_match_similarity_threshold:
                score += 35
            else:
                continue

            if normalized_text in {"群聊", "联系人", "聊天记录", "更多"}:
                score -= 60

            # Prefer the exact match that appears near the top of the result list.
            # In WeChat contact search, the first "联系人" result is often the safest hit.
            if normalized_text == normalized_target and item.top < 80:
                score += 30

            score += item.confidence * 10
            if score > best_score:
                best_score = score
                click_y = result_top + item.top + max(int(item.height * 2.0), 26)
                best_match = _OCRClickTarget(
                    text=item.text,
                    click_x=row_click_x,
                    click_y=click_y,
                    score=score,
                )

        return best_match

    def _search_result_region(
        self,
        *,
        window_x: int,
        window_y: int,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        result_left = window_x + int(width * 0.06)
        result_top = window_y + 52
        result_width = int(width * 0.84)
        result_height = int(height * 0.78)
        return result_left, result_top, result_width, result_height

    def _visible_chat_list_region(
        self,
        *,
        window_x: int,
        window_y: int,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        # Skip the global app sidebar on the far left and focus on the actual chat list.
        # Keep enough left margin to avoid the global sidebar, but start early enough
        # that contact titles near the avatar are not clipped at their first character.
        list_left = window_x + int(width * 0.12)
        list_top = window_y + 70
        list_width = int(width * 0.26)
        list_height = int(height * 0.80)
        return list_left, list_top, list_width, list_height

    def _visible_chat_badge_region(
        self,
        *,
        window_x: int,
        window_y: int,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        # Focus on the unread badge area near the chat avatar's top-right corner.
        # Keep it well away from the global app sidebar, but wide enough to fully
        # include the red badge instead of only clipping its edge.
        badge_left = window_x + int(width * 0.125)
        badge_top = window_y + 70
        badge_width = int(width * 0.075)
        badge_height = int(height * 0.80)
        return badge_left, badge_top, badge_width, badge_height

    def _read_visible_chat_entries(
        self,
        *,
        window_x: int,
        window_y: int,
        width: int,
        height: int,
        unread_only: bool,
    ) -> list[_VisibleChatEntry]:
        region_left, region_top, region_width, region_height = self._visible_chat_list_region(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )
        if region_width <= 0 or region_height <= 0:
            return []

        badge_left, badge_top, badge_width, badge_height = self._visible_chat_badge_region(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )
        unread_centers = self._detect_unread_badge_centers(
            left=badge_left,
            top=badge_top,
            width=badge_width,
            height=badge_height,
        )

        recognized = self._ocr.capture_and_recognize(
            left=region_left,
            top=region_top,
            width=region_width,
            height=region_height,
        )
        filtered = [
            item
            for item in recognized
            if item.text.strip()
            and item.confidence >= 0.2
            and item.left < int(region_width * 0.82)
            and not self._looks_like_time_text(item.text)
            and not self._looks_like_chat_list_noise(item.text)
        ]
        filtered.sort(key=lambda item: (item.top, item.left))

        lines: list[dict[str, object]] = []
        for item in filtered:
            if not lines:
                lines.append({"top": item.top, "left": item.left, "texts": [item.text.strip()]})
                continue

            current_line = lines[-1]
            if abs(item.top - int(current_line["top"])) <= 20:
                cast(list[str], current_line["texts"]).append(item.text.strip())
                current_line["left"] = min(int(current_line["left"]), item.left)
            else:
                lines.append({"top": item.top, "left": item.left, "texts": [item.text.strip()]})

        merged_lines: list[tuple[int, int, str]] = []
        for line in lines:
            text = " ".join(cast(list[str], line["texts"])).strip()
            if text:
                merged_lines.append((int(line["top"]), int(line["left"]), text))

        rows: list[list[tuple[int, int, str]]] = []
        for line in merged_lines:
            if not rows or line[0] - rows[-1][-1][0] > 34:
                rows.append([line])
            else:
                rows[-1].append(line)

        entries: list[_VisibleChatEntry] = []
        seen_titles: set[str] = set()
        row_click_x = window_x + int(width * 0.18)

        for row in rows:
            title_candidates = [
                line for line in row if line[1] < int(region_width * 0.34) and not self._looks_like_chat_snippet(line[2])
            ]
            if not title_candidates:
                title_candidates = [line for line in row if not self._looks_like_chat_snippet(line[2])]
            if not title_candidates:
                continue

            title_line = min(title_candidates, key=lambda item: (item[0], item[1]))
            title = title_line[2].strip()
            normalized_title = self._normalize_text(title)
            if not normalized_title or normalized_title in seen_titles:
                continue

            top_values = [line[0] for line in row]
            bottom_values = [line[0] + 24 for line in row]
            row_top = min(top_values)
            row_bottom = max(bottom_values)
            if unread_only and not any(row_top - 10 <= center <= row_bottom + 10 for center in unread_centers):
                continue
            click_y = region_top + ((min(top_values) + max(bottom_values)) // 2) + 6
            entries.append(
                _VisibleChatEntry(
                    title=title,
                    click_x=row_click_x,
                    click_y=click_y,
                )
            )
            seen_titles.add(normalized_title)

        return entries

    def _detect_unread_badge_centers(
        self,
        *,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> list[int]:
        capture_path = self._ocr._capture_region(left=left, top=top, width=width, height=height)
        try:
            image = Image.open(capture_path).convert("RGB")
            image_width, image_height = image.size
            centers = self._find_red_badge_centers(capture_path)
            if centers:
                return self._scale_badge_centers(centers, source_height=image_height, target_height=height)
            centers = self._find_red_badge_centers_by_rows(capture_path)
            return self._scale_badge_centers(centers, source_height=image_height, target_height=height)
        finally:
            capture_path.unlink(missing_ok=True)

    def _scale_badge_centers(
        self,
        centers: list[int],
        *,
        source_height: int,
        target_height: int,
    ) -> list[int]:
        if not centers or source_height <= 0 or target_height <= 0:
            return centers
        if source_height == target_height:
            return centers

        scale = target_height / float(source_height)
        scaled = [max(0, min(target_height - 1, int(round(center * scale)))) for center in centers]
        scaled.sort()

        deduped: list[int] = []
        for center in scaled:
            if deduped and abs(center - deduped[-1]) <= 6:
                deduped[-1] = (deduped[-1] + center) // 2
            else:
                deduped.append(center)
        return deduped

    def _find_red_badge_centers(self, image_path: Path) -> list[int]:
        image = Image.open(image_path).convert("RGB")
        pixel_access = image.load()
        width, height = image.size
        visited: set[tuple[int, int]] = set()
        centers: list[int] = []

        for y in range(height):
            for x in range(width):
                if (x, y) in visited:
                    continue
                if not self._is_unread_badge_red(pixel_access[x, y]):
                    continue

                stack = [(x, y)]
                visited.add((x, y))
                min_x = max_x = x
                min_y = max_y = y
                count = 0

                while stack:
                    current_x, current_y = stack.pop()
                    count += 1
                    min_x = min(min_x, current_x)
                    max_x = max(max_x, current_x)
                    min_y = min(min_y, current_y)
                    max_y = max(max_y, current_y)

                    for next_x, next_y in (
                        (current_x + 1, current_y),
                        (current_x - 1, current_y),
                        (current_x, current_y + 1),
                        (current_x, current_y - 1),
                    ):
                        if not (0 <= next_x < width and 0 <= next_y < height):
                            continue
                        if (next_x, next_y) in visited:
                            continue
                        if not self._is_unread_badge_red(pixel_access[next_x, next_y]):
                            continue
                        visited.add((next_x, next_y))
                        stack.append((next_x, next_y))

                box_width = max_x - min_x + 1
                box_height = max_y - min_y + 1
                center_x = (min_x + max_x) // 2
                if count < 8 or count > 2400:
                    continue
                if box_width < 4 or box_height < 4:
                    continue
                if box_width > 80 or box_height > 80:
                    continue
                # Unread badges are small, near-circular red blobs around the avatar area.
                # This filters out larger or elongated red regions inside avatars/content.
                if abs(box_width - box_height) > 12:
                    continue
                fill_ratio = count / float(box_width * box_height)
                if fill_ratio < 0.22:
                    continue
                # In the dedicated badge strip, badges should stay inside the strip
                # but can be closer to the left edge after region tightening.
                if center_x < int(width * 0.10) or center_x > int(width * 0.95):
                    continue
                centers.append((min_y + max_y) // 2)

        centers.sort()
        deduped: list[int] = []
        for center in centers:
            if deduped and abs(center - deduped[-1]) <= 10:
                deduped[-1] = (deduped[-1] + center) // 2
            else:
                deduped.append(center)
        return deduped

    def _find_red_badge_centers_by_rows(self, image_path: Path) -> list[int]:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        pixel_access = image.load()

        row_scores: list[int] = []
        for y in range(height):
            score = 0
            for x in range(width):
                if self._is_unread_badge_red(pixel_access[x, y]):
                    score += 1
            row_scores.append(score)

        if not row_scores:
            return []

        threshold = max(3, int(width * 0.10))
        centers: list[int] = []
        start: int | None = None

        for index, score in enumerate(row_scores):
            if score >= threshold:
                if start is None:
                    start = index
                continue

            if start is not None:
                end = index - 1
                if end - start + 1 >= 4:
                    centers.append((start + end) // 2)
                start = None

        if start is not None:
            end = len(row_scores) - 1
            if end - start + 1 >= 4:
                centers.append((start + end) // 2)

        deduped: list[int] = []
        for center in centers:
            if deduped and abs(center - deduped[-1]) <= 10:
                deduped[-1] = (deduped[-1] + center) // 2
            else:
                deduped.append(center)
        return deduped

    def _is_unread_badge_red(self, rgb: tuple[int, int, int]) -> bool:
        red, green, blue = rgb
        return (
            red >= 150
            and green <= 170
            and blue <= 170
            and (red - green) >= 20
            and (red - blue) >= 15
        )

    def debug_search_target_with_ocr(
        self,
        *,
        target: str,
    ) -> dict[str, object]:
        geometry = self._window_geometry()
        if geometry is None:
            return {
                "window_geometry": None,
                "ocr_region": None,
                "ocr_candidates": [],
                "click_target": None,
            }

        window_x, window_y, width, height = geometry
        result_left, result_top, result_width, result_height = self._search_result_region(
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )

        recognized = self._ocr.capture_and_recognize(
            left=result_left,
            top=result_top,
            width=result_width,
            height=result_height,
        )
        click_target = self._select_search_result_with_ocr(
            target=target,
            window_x=window_x,
            window_y=window_y,
            width=width,
            height=height,
        )

        return {
            "window_geometry": geometry,
            "ocr_region": (result_left, result_top, result_width, result_height),
            "ocr_candidates": recognized,
            "click_target": click_target,
        }

    def _is_ocr_noise_text(self, normalized_text: str) -> bool:
        if normalized_text.startswith("包含"):
            return True
        if normalized_text.startswith("网络查找"):
            return True
        if normalized_text.startswith("搜索"):
            return True
        if normalized_text in {"群聊", "联系人", "聊天记录", "更多"}:
            return True
        return False

    def _verify_active_chat(self, target: str) -> bool:
        geometry = self._window_geometry()
        if geometry is None:
            return False

        window_x, window_y, width, _ = geometry
        normalized_target = self._normalize_chat_name(target)
        if not normalized_target:
            return False

        for region in self._active_chat_verification_regions(
            window_x=window_x,
            window_y=window_y,
            width=width,
        ):
            recognized = self._ocr.capture_and_recognize(
                left=region[0],
                top=region[1],
                width=region[2],
                height=region[3],
            )

            for item in recognized:
                normalized_text = self._normalize_chat_name(item.text)
                if not normalized_text:
                    continue
                if self._is_similar_chat_match(
                    normalized_target=normalized_target,
                    normalized_text=normalized_text,
                ):
                    return True

        return False

    def _wait_for_active_chat(self, target: str) -> bool:
        for _ in range(4):
            self._delay(0.3)
            if self._verify_active_chat(target):
                return True

        return False

    def _active_chat_verification_regions(
        self,
        *,
        window_x: int,
        window_y: int,
        width: int,
    ) -> list[tuple[int, int, int, int]]:
        header_left = window_x + int(width * 0.40)
        header_top = window_y + 10
        header_width = int(width * 0.43)
        header_height = 88

        # Fallback region slightly lower and wider to tolerate title rendering lag.
        fallback_left = window_x + int(width * 0.36)
        fallback_top = window_y + 6
        fallback_width = int(width * 0.52)
        fallback_height = 110

        regions = [
            (header_left, header_top, header_width, header_height),
            (fallback_left, fallback_top, fallback_width, fallback_height),
        ]
        return [region for region in regions if region[2] > 0 and region[3] > 0]

    def _read_active_chat_title(self, *, window_x: int, window_y: int, width: int) -> str:
        regions = self._active_chat_verification_regions(
            window_x=window_x,
            window_y=window_y,
            width=width,
        )
        title_candidates: list[tuple[int, str]] = []

        for region in regions:
            recognized = self._ocr.capture_and_recognize(
                left=region[0],
                top=region[1],
                width=region[2],
                height=region[3],
            )
            line_items = [
                item
                for item in recognized
                if item.text.strip()
                and item.left < int(region[2] * 0.72)
                and item.top < int(region[3] * 0.75)
                and not self._looks_like_header_noise(item.text)
            ]
            if not line_items:
                continue

            line_items.sort(key=lambda item: (item.top, item.left))
            merged_lines: list[tuple[int, list[str]]] = []
            for item in line_items:
                if not merged_lines or abs(item.top - merged_lines[-1][0]) > 16:
                    merged_lines.append((item.top, [item.text.strip()]))
                else:
                    merged_lines[-1][1].append(item.text.strip())

            for top, texts in merged_lines:
                merged = "".join(texts).strip()
                if merged:
                    title_candidates.append((top, merged))

        if not title_candidates:
            return ""

        title_candidates.sort(key=lambda item: (item[0], -len(item[1])))
        return title_candidates[0][1]

    def _read_visible_message_lines(
        self,
        *,
        window_x: int,
        window_y: int,
        width: int,
        height: int,
        is_group_chat: bool,
    ) -> list[dict[str, str]]:
        message_left = window_x + int(width * 0.44)
        message_top = window_y + 68
        message_width = int(width * 0.52)
        message_height = int(height * 0.80)
        if message_width <= 0 or message_height <= 0:
            return []

        recognized = self._ocr.capture_and_recognize(
            left=message_left,
            top=message_top,
            width=message_width,
            height=message_height,
        )
        filtered = [
            item
            for item in recognized
            if item.text.strip()
            and item.confidence >= 0.2
            and item.left < int(message_width * 0.78)
            and item.top >= 0
            and not self._is_message_ocr_noise(item.text)
            and not self._looks_like_top_notification_text(item.text, top=item.top)
        ]
        filtered.sort(key=lambda item: (item.top, item.left))

        lines: list[dict[str, object]] = []
        for item in filtered:
            if not lines:
                lines.append({"top": item.top, "left": item.left, "texts": [item.text.strip()]})
                continue

            current_line = lines[-1]
            if abs(item.top - int(current_line["top"])) <= 22:
                texts = cast(list[str], current_line["texts"])
                texts.append(item.text.strip())
                current_line["left"] = min(int(current_line["left"]), item.left)
            else:
                lines.append({"top": item.top, "left": item.left, "texts": [item.text.strip()]})

        merged_lines: list[tuple[int, int, str]] = []
        for line in lines:
            texts = cast(list[str], line["texts"])
            merged = " ".join(texts).strip()
            if merged:
                merged_lines.append((int(line["top"]), int(line["left"]), merged))

        # Merge nearby visual lines into message blocks. A long chat bubble often spans
        # multiple OCR lines, and we want one message block instead of one entry per line.
        #
        # In group chats, sender names appear as short labels above each bubble. Those
        # labels should separate messages but should not be included in message content.
        message_blocks: list[dict[str, object]] = []
        pending_sender_name: str | None = None

        for index, (top, left, text) in enumerate(merged_lines):
            next_text = merged_lines[index + 1][2] if index + 1 < len(merged_lines) else ""
            next_top = merged_lines[index + 1][0] if index + 1 < len(merged_lines) else None

            if is_group_chat and self._looks_like_sender_name(
                text,
                current_left=left,
                next_text=next_text,
                current_top=top,
                next_top=next_top,
            ):
                if pending_sender_name is not None:
                    message_blocks.append(
                        {
                            "top": top,
                            "parts": ["[非文本消息]"],
                            "sender": pending_sender_name,
                        }
                    )
                pending_sender_name = text.strip()
                continue

            if not message_blocks:
                message_blocks.append(
                    {
                        "top": top,
                        "parts": [text],
                        "sender": pending_sender_name or "",
                    }
                )
                pending_sender_name = None
                continue

            previous = message_blocks[-1]
            previous_top = int(previous["top"])
            previous_parts = cast(list[str], previous["parts"])

            if pending_sender_name is not None:
                message_blocks.append(
                    {
                        "top": top,
                        "parts": [text],
                        "sender": pending_sender_name,
                    }
                )
                pending_sender_name = None
            elif self._should_merge_message_lines(
                previous_text=previous_parts[-1],
                current_text=text,
                gap=top - previous_top,
            ):
                previous_parts.append(text)
                previous["top"] = top
            else:
                message_blocks.append({"top": top, "parts": [text], "sender": ""})
        if is_group_chat and pending_sender_name is not None:
            message_blocks.append(
                {
                    "top": merged_lines[-1][0] if merged_lines else 0,
                    "parts": ["[非文本消息]"],
                    "sender": pending_sender_name,
                }
            )

        merged_messages: list[dict[str, str]] = []
        for block in message_blocks:
            parts = cast(list[str], block["parts"])
            text = "\n".join(parts).strip()
            if text:
                merged_messages.append(
                    self._message_payload(
                        text,
                        sender=str(block.get("sender", "")).strip(),
                    )
                )

        return merged_messages

    def _message_payload(self, text: str, *, sender: str = "") -> dict[str, str]:
        stripped = text.strip()
        return {
            "content": stripped,
            "sender": sender,
            "kind": self._message_kind(stripped),
        }

    def _message_kind(self, text: str) -> str:
        if text == "[非文本消息]":
            return "non_text"
        if "撤回了一条消息" in text:
            return "system"
        if "群公告" in text or "加入群聊" in text or "以下为新消息" in text:
            return "notification"
        return "text"

    def _is_message_ocr_noise(self, text: str) -> bool:
        stripped = text.strip()
        normalized = self._normalize_text(text)
        if not normalized:
            return True
        if normalized in {"搜索", "更多", "联系人", "群聊"}:
            return True
        if normalized.startswith("网络查找"):
            return True
        if "新消息" in text:
            return True
        if text.startswith("^"):
            return True
        if "@" in text and len(stripped) <= 24:
            return True
        if any(symbol in stripped for symbol in ("<", ">", "«", "»")) and len(stripped) <= 4:
            return True
        if re.fullmatch(r"[\dOoIl]{1,4}[.,:：]?", stripped):
            return True
        if re.fullmatch(r"[\dA-Za-z]{1,5}[.,:：][\dA-Za-z]{1,5}", stripped):
            return True
        if self._looks_like_time_text(text):
            return True
        return False

    def _looks_like_sender_name(
        self,
        text: str,
        *,
        current_left: int,
        next_text: str,
        current_top: int,
        next_top: int | None,
    ) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if self._is_message_ocr_noise(stripped):
            return False
        if len(stripped) > 10:
            return False
        if current_left > 32:
            return False
        if any(token in stripped for token in ("：", ":", "。", "，", ".", ",")):
            return False

        if next_top is None:
            return True

        gap = next_top - current_top
        if gap > 120:
            return True
        if gap > 72:
            return False

        next_stripped = next_text.strip()
        if not next_stripped:
            return True
        if len(next_stripped) < len(stripped):
            return False
        return True

    def _should_merge_message_lines(self, *, previous_text: str, current_text: str, gap: int) -> bool:
        if gap <= 0:
            return True

        prev = previous_text.strip()
        curr = current_text.strip()
        if not prev or not curr:
            return False

        # Short plain-text bubbles should stay separated unless they are extremely close.
        if gap <= 24:
            return True

        previous_is_structured = self._is_structured_message_line(prev)
        current_is_structured = self._is_structured_message_line(curr)

        if previous_is_structured or current_is_structured:
            return gap <= 78

        return gap <= 30

    def _is_structured_message_line(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if len(stripped) >= 12:
            return True
        if stripped.endswith(("：", ":")):
            return True
        if stripped.startswith(("1.", "2.", "3.", "4.", "-", "•")):
            return True
        if any(token in stripped for token in ("昨日", "今日", "需求", "日常", "参与人员", "站会", "冲刺")):
            return True
        return False

    def _looks_like_time_text(self, text: str) -> bool:
        return bool(self._TIME_PATTERN.match(text.strip()))

    def _looks_like_header_noise(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        if self._looks_like_time_text(stripped):
            return True
        normalized = self._normalize_text(stripped)
        if normalized in {"搜索", "更多"}:
            return True
        return False

    def _looks_like_top_notification_text(self, text: str, *, top: int) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if top > 28:
            return False

        lowered = stripped.lower()
        if "http://" in lowered or "https://" in lowered or "www." in lowered:
            return True
        if stripped.endswith(">") or stripped.endswith("›") or stripped.endswith("..."):
            return True
        if "@" in stripped and len(stripped) >= 6:
            return True
        if "：" in stripped or ":" in stripped:
            if len(stripped) >= 8:
                return True
        return False

    def _looks_like_chat_list_noise(self, text: str) -> bool:
        stripped = text.strip()
        normalized = self._normalize_text(stripped)
        if not normalized:
            return True
        if normalized in {"搜索", "群聊", "微信支付"}:
            return True
        if normalized.startswith("你撤回了一条消息"):
            return False
        if "http://" in stripped.lower() or "https://" in stripped.lower():
            return False
        if stripped.endswith("...") and len(stripped) <= 6:
            return True
        return False

    def _looks_like_chat_snippet(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        if self._looks_like_time_text(stripped):
            return True
        if stripped.startswith(("你", "群", "陈", "阿", "奶", "亚")) and "：" in stripped:
            return True
        if stripped.startswith("http://") or stripped.startswith("https://"):
            return True
        if stripped.startswith("[") and stripped.endswith("]"):
            return True
        if "你撤回了一条消息" in stripped:
            return True
        return False

    def _find_matching_elements(
        self,
        target: str,
        left_pane_max_x: int,
        search_area_top_y: int,
        search_area_bottom_y: int,
    ) -> list[_AXMatchCandidate]:
        process = self._application_element()
        if process is None:
            return []

        normalized_target = self._normalize_chat_name(target)
        candidates: list[_AXMatchCandidate] = []

        for node in self._iter_accessibility_tree(process):
            element = node.element
            depth = node.depth
            if depth > 10:
                continue

            role = self._ax_string(element, kAXRoleAttribute)
            text_variants = self._element_texts(element)
            if not text_variants:
                continue

            position = self._ax_point(element, kAXPositionAttribute, kAXValueCGPointType)
            size = self._ax_size(element, kAXSizeAttribute, kAXValueCGSizeType)
            if position is None:
                position = node.inherited_position
            if size is None:
                size = node.inherited_size
            if position is None or size is None:
                continue

            center_x = int(position.x + (size.width / 2))
            center_y = int(position.y + (size.height / 2))

            if center_x > left_pane_max_x:
                continue
            if center_y < search_area_top_y or center_y > search_area_bottom_y:
                continue

            for text in text_variants:
                normalized_text = self._normalize_chat_name(text)
                if not normalized_text:
                    continue

                score = self._match_score(
                    normalized_target=normalized_target,
                    normalized_text=normalized_text,
                    role=role,
                )
                if score <= 0:
                    continue

                candidates.append(
                    _AXMatchCandidate(
                        text=text,
                        center_x=center_x,
                        center_y=center_y,
                        score=score,
                    )
                )

        return candidates

    def _match_score(self, normalized_target: str, normalized_text: str, role: str) -> int:
        score = 0
        if normalized_text == normalized_target:
            score += 100
        elif normalized_target in normalized_text:
            score += 40
        elif self._chat_match_similarity(
            normalized_target=normalized_target,
            normalized_text=normalized_text,
        ) >= self._settings.chat_match_similarity_threshold:
            score += 28
        else:
            return 0

        if role in {"AXStaticText", "AXTextField"}:
            score += 10
        elif role in {"AXRow", "AXGroup", "AXButton"}:
            score += 6

        score += max(0, 10 - abs(len(normalized_text) - len(normalized_target)))
        return score

    def _normalize_text(self, text: str) -> str:
        return "".join(text.split()).casefold()

    def _searchable_chat_name(self, text: str) -> str:
        return self._strip_group_member_count(text).strip()

    def _normalize_chat_name(self, text: str) -> str:
        return self._normalize_text(self._searchable_chat_name(text))

    def _strip_group_member_count(self, text: str) -> str:
        stripped = text.strip()
        return re.sub(r"\s*[（(]\d+[）)]\s*$", "", stripped)

    def _chat_match_similarity(self, *, normalized_target: str, normalized_text: str) -> float:
        if not normalized_target or not normalized_text:
            return 0.0
        if normalized_target == normalized_text:
            return 1.0
        if normalized_target in normalized_text or normalized_text in normalized_target:
            shorter = min(len(normalized_target), len(normalized_text))
            longer = max(len(normalized_target), len(normalized_text))
            return 0.0 if longer == 0 else shorter / longer
        return SequenceMatcher(None, normalized_target, normalized_text).ratio()

    def _is_similar_chat_match(self, *, normalized_target: str, normalized_text: str) -> bool:
        if not normalized_target or not normalized_text:
            return False
        if normalized_text == normalized_target:
            return True
        if normalized_target in normalized_text and len(normalized_text) <= len(normalized_target) + 4:
            return True
        return self._chat_match_similarity(
            normalized_target=normalized_target,
            normalized_text=normalized_text,
        ) >= self._settings.chat_match_similarity_threshold

    def _element_texts(self, element: Any) -> list[str]:
        texts = [
            self._ax_string(element, kAXTitleAttribute),
            self._ax_string(element, kAXValueAttribute),
            self._ax_string(element, kAXDescriptionAttribute),
        ]
        children = self._ax_attribute(element, kAXChildrenAttribute)
        if isinstance(children, list):
            for child in children[:8]:
                texts.extend(
                    [
                        self._ax_string(child, kAXTitleAttribute),
                        self._ax_string(child, kAXValueAttribute),
                        self._ax_string(child, kAXDescriptionAttribute),
                    ]
                )
        unique: list[str] = []
        for text in texts:
            if text and text not in unique:
                unique.append(text)
        return unique

    def _focused_window(self) -> Any | None:
        process = self._application_element()
        if process is None:
            return None

        focused_window = self._ax_attribute(process, kAXFocusedWindowAttribute)
        if focused_window is not None:
            return focused_window

        windows = self._ax_attribute(process, kAXWindowsAttribute)
        if isinstance(windows, list) and windows:
            return windows[0]
        return None

    def _application_element(self) -> Any | None:
        pid = self._resolve_pid()
        if pid is None:
            return None
        return AXUIElementCreateApplication(pid)

    def _resolve_pid(self) -> int | None:
        for app_name in self._app_names:
            completed = subprocess.run(
                ["pgrep", "-x", app_name],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                first_line = completed.stdout.strip().splitlines()[0]
                try:
                    return int(first_line)
                except ValueError:
                    continue
        return None

    def _iter_accessibility_tree(self, root: Any) -> list[_AXTraversalNode]:
        nodes: list[_AXTraversalNode] = []
        queue: list[_AXTraversalNode] = [
            _AXTraversalNode(
                element=root,
                depth=0,
                inherited_position=None,
                inherited_size=None,
            )
        ]

        while queue and len(nodes) < 2500:
            node = queue.pop(0)
            nodes.append(node)
            element = node.element
            depth = node.depth
            position = self._ax_point(element, kAXPositionAttribute, kAXValueCGPointType) or node.inherited_position
            size = self._ax_size(element, kAXSizeAttribute, kAXValueCGSizeType) or node.inherited_size
            children = self._ax_attribute(element, kAXChildrenAttribute)
            if isinstance(children, list):
                queue.extend(
                    _AXTraversalNode(
                        element=child,
                        depth=depth + 1,
                        inherited_position=position,
                        inherited_size=size,
                    )
                    for child in children
                )

        return nodes

    def _ax_attribute(self, element: Any, attribute: str) -> Any | None:
        error_code, value = AXUIElementCopyAttributeValue(element, attribute, None)
        if error_code != 0:
            return None
        return value

    def _ax_string(self, element: Any, attribute: str) -> str:
        value = self._ax_attribute(element, attribute)
        if isinstance(value, str):
            return value
        return ""

    def _ax_point(self, element: Any, attribute: str, value_type: int) -> Any | None:
        value = self._ax_attribute(element, attribute)
        if value is None:
            return None
        ok, point = AXValueGetValue(value, value_type, None)
        if not ok:
            return None
        return point

    def _ax_size(self, element: Any, attribute: str, value_type: int) -> Any | None:
        value = self._ax_attribute(element, attribute)
        if value is None:
            return None
        ok, size = AXValueGetValue(value, value_type, None)
        if not ok:
            return None
        return size

    def _click_point(self, x: int, y: int) -> None:
        try:
            import pyautogui
        except ImportError as exc:
            raise DriverError("pyautogui is required for mouse clicking.") from exc

        pyautogui.click(x, y)
