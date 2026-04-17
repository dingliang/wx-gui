from __future__ import annotations

from app.application.dto.auto_reply import AutoReplyRuleDTO
from app.application.dto.read_messages_result import ChatMessageDTO
from app.application.dto.read_visible_chats_result import ChatSnapshotDTO
from app.application.usecases.plan_auto_replies import PlanAutoRepliesUseCase


def test_plan_auto_replies_matches_keyword_and_skips_non_text() -> None:
    use_case = PlanAutoRepliesUseCase()
    chats = [
        ChatSnapshotDTO(
            chat_title="sample-chat",
            messages=[
                ChatMessageDTO(content="你好，在吗", kind="text", sender="alice"),
                ChatMessageDTO(content="[非文本消息]", kind="non_text", sender="alice"),
            ],
        )
    ]
    rules = [
        AutoReplyRuleDTO(trigger="你好", reply_text="你好，我稍后回复你。"),
        AutoReplyRuleDTO(trigger="在吗", reply_text="在的。"),
    ]

    result = use_case.execute(chats=chats, rules=rules, handled_signatures=set())

    assert len(result.actions) == 1
    assert result.actions[0].chat_title == "sample-chat"
    assert result.actions[0].reply_text == "你好，我稍后回复你。"
    assert result.actions[0].sender == "alice"


def test_plan_auto_replies_respects_handled_signatures() -> None:
    use_case = PlanAutoRepliesUseCase()
    chat = ChatSnapshotDTO(
        chat_title="sample-chat",
        messages=[ChatMessageDTO(content="收到吗", kind="text", sender="alice")],
    )
    rules = [AutoReplyRuleDTO(trigger="收到", reply_text="收到。")]
    handled = {"sample-chat|alice|text|收到吗"}

    result = use_case.execute(chats=[chat], rules=rules, handled_signatures=handled)

    assert result.actions == []
