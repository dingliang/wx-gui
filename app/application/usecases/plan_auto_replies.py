from __future__ import annotations

from app.application.dto.auto_reply import AutoReplyActionDTO, AutoReplyPlanResultDTO, AutoReplyRuleDTO
from app.application.dto.read_visible_chats_result import ChatSnapshotDTO


class PlanAutoRepliesUseCase:
    def execute(
        self,
        *,
        chats: list[ChatSnapshotDTO],
        rules: list[AutoReplyRuleDTO],
        handled_signatures: set[str],
    ) -> AutoReplyPlanResultDTO:
        if not rules:
            return AutoReplyPlanResultDTO(message="No auto-reply rules configured.")

        actions: list[AutoReplyActionDTO] = []
        ignored_signatures: list[str] = []

        for chat in chats:
            for message in chat.messages:
                signature = self._message_signature(chat.chat_title, message.sender, message.kind, message.content)
                if signature in handled_signatures:
                    continue
                if not self._is_replyable_message(message.kind, message.content):
                    ignored_signatures.append(signature)
                    continue

                rule = self._match_rule(message.content, rules)
                if rule is None:
                    continue

                actions.append(
                    AutoReplyActionDTO(
                        chat_title=chat.chat_title,
                        trigger_content=message.content,
                        reply_text=rule.reply_text,
                        sender=message.sender,
                        message_signature=signature,
                    )
                )

        return AutoReplyPlanResultDTO(
            actions=actions,
            ignored_signatures=ignored_signatures,
            message=f"Planned {len(actions)} auto replies.",
        )

    def _match_rule(self, content: str, rules: list[AutoReplyRuleDTO]) -> AutoReplyRuleDTO | None:
        normalized_content = self._normalize_text(content)
        if not normalized_content:
            return None

        for rule in rules:
            trigger = self._normalize_text(rule.trigger)
            if not trigger:
                continue
            if rule.match_mode == "exact":
                if normalized_content == trigger:
                    return rule
                continue
            if trigger in normalized_content:
                return rule
        return None

    def _is_replyable_message(self, kind: str, content: str) -> bool:
        normalized_content = self._normalize_text(content)
        if not normalized_content:
            return False
        if kind != "text":
            return False
        if normalized_content == "[非文本消息]":
            return False
        return True

    def _normalize_text(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

    def _message_signature(self, chat_title: str, sender: str, kind: str, content: str) -> str:
        return f"{chat_title}|{sender}|{kind}|{content}"
