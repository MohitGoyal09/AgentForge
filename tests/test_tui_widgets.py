from __future__ import annotations
import pytest
from agentforge_harness.ui.state import ChatItem
from agentforge_harness.ui.config import DEFAULT_THEME
from agentforge_harness.ui.widgets import (
    TranscriptView, SessionSidebar, _format_role_label, _item_to_markup,
)
from textual.widget import Widget

def test_format_role_label_user():
    label = _format_role_label("user", DEFAULT_THEME)
    assert "you" in label or "user" in label

def test_item_to_markup_assistant():
    item = ChatItem(role="assistant", text="hello world")
    markup = _item_to_markup(item, DEFAULT_THEME)
    assert "hello world" in markup

def test_item_to_markup_error():
    item = ChatItem(role="error", text="something broke")
    markup = _item_to_markup(item, DEFAULT_THEME)
    assert "something broke" in markup

def test_item_to_markup_thinking_hidden():
    item = ChatItem(role="thinking", text="internal reasoning")
    markup = _item_to_markup(item, DEFAULT_THEME, show_thinking=False)
    assert "internal reasoning" not in markup

def test_transcript_view_is_widget():
    assert issubclass(TranscriptView, Widget)

def test_session_sidebar_is_widget():
    assert issubclass(SessionSidebar, Widget)
