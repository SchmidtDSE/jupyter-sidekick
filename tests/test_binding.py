"""ChatBinding: per-chat state machine. Draft until bound; immutable after."""
from __future__ import annotations

import pytest

from jupyter_acp_chat.binding import AlreadyBoundError, ChatBinding, NotBoundError


class _FakeSession:
    pass


def test_initial_state_is_draft():
    binding = ChatBinding("chat-1")
    assert binding.is_draft
    assert not binding.is_bound
    assert binding.harness_id is None


def test_bind_transitions_to_bound():
    binding = ChatBinding("chat-1")
    session = _FakeSession()
    binding.bind("claude-code", session)
    assert binding.is_bound
    assert not binding.is_draft
    assert binding.harness_id == "claude-code"
    assert binding.session is session


def test_double_bind_raises():
    binding = ChatBinding("chat-1")
    binding.bind("x", _FakeSession())
    with pytest.raises(AlreadyBoundError):
        binding.bind("y", _FakeSession())


def test_session_when_unbound_raises():
    binding = ChatBinding("chat-1")
    with pytest.raises(NotBoundError):
        _ = binding.session
