"""Task vagueness heuristic: no verb / >10 words → nudge for next_action."""

from __future__ import annotations

import re

# Common English + Vietnamese action verbs (lowercase)
_VERBS = {
    # EN
    "call",
    "write",
    "send",
    "email",
    "open",
    "check",
    "review",
    "fix",
    "update",
    "create",
    "add",
    "delete",
    "remove",
    "buy",
    "order",
    "schedule",
    "book",
    "meet",
    "ask",
    "reply",
    "read",
    "draft",
    "submit",
    "upload",
    "download",
    "install",
    "run",
    "test",
    "deploy",
    "merge",
    "push",
    "pull",
    "build",
    "start",
    "finish",
    "complete",
    "prepare",
    "print",
    "file",
    "pay",
    "confirm",
    "verify",
    "clean",
    "move",
    "copy",
    "paste",
    "find",
    "search",
    "look",
    "go",
    "get",
    "put",
    "set",
    "make",
    "do",
    "plan",
    "organize",
    "sort",
    "ship",
    "track",
    "measure",
    "count",
    "calculate",
    "sign",
    "approve",
    "reject",
    "discuss",
    "talk",
    "visit",
    "attend",
    "pick",
    "drop",
    "return",
    "replace",
    "rename",
    "refactor",
    "document",
    "sync",
    "backup",
    "restore",
    "configure",
    "setup",
    "set-up",
    # VN (common infinitive-ish / command forms)
    "gọi",
    "viết",
    "gửi",
    "mở",
    "kiểm",
    "kiểm tra",
    "sửa",
    "cập nhật",
    "tạo",
    "thêm",
    "xóa",
    "mua",
    "đặt",
    "hẹn",
    "hỏi",
    "trả lời",
    "đọc",
    "soạn",
    "nộp",
    "tải",
    "cài",
    "chạy",
    "thử",
    "deploy",
    "bắt đầu",
    "hoàn thành",
    "chuẩn bị",
    "in",
    "thanh toán",
    "xác nhận",
    "dọn",
    "chuyển",
    "tìm",
    "lên kế hoạch",
    "sắp xếp",
    "giao",
    "theo dõi",
    "đo",
    "đếm",
    "ký",
    "duyệt",
    "thảo luận",
    "nói",
    "gặp",
    "đi",
    "lấy",
    "đặt lại",
}


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text.strip()))


def has_verb(text: str) -> bool:
    lower = text.strip().lower()
    # multi-word verbs first
    for verb in sorted(_VERBS, key=len, reverse=True):
        if " " in verb:
            if verb in lower:
                return True
    tokens = re.findall(r"[\w'-]+", lower, flags=re.UNICODE)
    if not tokens:
        return False
    # first token or any token match
    for t in tokens[:4]:
        if t in _VERBS:
            return True
    return False


def looks_vague(title: str, next_action: str | None = None) -> bool:
    """True when UI should nudge for next_action."""
    if next_action and next_action.strip():
        return False
    title = (title or "").strip()
    if not title:
        return False
    if word_count(title) > 10:
        return True
    if not has_verb(title):
        return True
    return False
