from types import SimpleNamespace

from xong.api import auth_context
from xong.auth import AuthContext


def test_auth_context_distinguishes_agent_from_subject():
    context = AuthContext(
        user=SimpleNamespace(username="user-one"),
        actor="agent",
        is_agent=True,
    )

    assert auth_context(context).model_dump() == {
        "actor": "agent",
        "subject": "user-one",
        "is_agent": True,
    }
