from __future__ import annotations

import pytest

from agentforge_harness.agent.session_tree import (
    COMPACTION_PREFIX,
    KIND_COMPACTION,
    KIND_LEAF,
    KIND_MESSAGE,
    SessionEntry,
    active_leaf_id,
    path_to_entry,
    reconstruct_messages,
)

TS = "2024-01-01T00:00:00"


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trips
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_message_roundtrip(self):
        entry = SessionEntry.message(
            parent_id="parent_abc",
            timestamp=TS,
            role="user",
            content="hello",
            tool_call_id="tc1",
            tool_calls=[{"id": "tc1", "function": {"name": "read_file"}}],
            token_count=5,
            entry_id="msg_001",
        )
        restored = SessionEntry.from_dict(entry.to_dict())

        assert restored.id == "msg_001"
        assert restored.parent_id == "parent_abc"
        assert restored.timestamp == TS
        assert restored.kind == KIND_MESSAGE
        assert restored.payload["role"] == "user"
        assert restored.payload["content"] == "hello"
        assert restored.payload["tool_call_id"] == "tc1"
        assert restored.payload["tool_calls"] == [{"id": "tc1", "function": {"name": "read_file"}}]
        assert restored.payload["token_count"] == 5

    def test_compaction_roundtrip(self):
        entry = SessionEntry.compaction(
            parent_id=None,
            timestamp=TS,
            summary="The user asked about Python.",
            replaces=["id_a", "id_b"],
            summary_tokens=42,
            entry_id="cmp_001",
        )
        restored = SessionEntry.from_dict(entry.to_dict())

        assert restored.id == "cmp_001"
        assert restored.parent_id is None
        assert restored.kind == KIND_COMPACTION
        assert restored.payload["summary"] == "The user asked about Python."
        assert restored.payload["replaces"] == ["id_a", "id_b"]
        assert restored.payload["summary_tokens"] == 42


# ---------------------------------------------------------------------------
# path_to_entry
# ---------------------------------------------------------------------------


class TestPathToEntry:
    def _linear_chain(self):
        """e1 <- e2 <- e3 (root is e1)."""
        e1 = SessionEntry.message(None, TS, "user", "one", entry_id="e1")
        e2 = SessionEntry.message("e1", TS, "assistant", "two", entry_id="e2")
        e3 = SessionEntry.message("e2", TS, "user", "three", entry_id="e3")
        return e1, e2, e3

    def test_linear_chain_order(self):
        e1, e2, e3 = self._linear_chain()
        result = path_to_entry([e1, e2, e3], "e3")
        assert [e.id for e in result] == ["e1", "e2", "e3"]

    def test_branch_path_to_right(self):
        """Fork: e1 is root; e2 and e3 both have e1 as parent."""
        e1 = SessionEntry.message(None, TS, "user", "root", entry_id="e1")
        e2 = SessionEntry.message("e1", TS, "assistant", "branch-a", entry_id="e2")
        e3 = SessionEntry.message("e1", TS, "assistant", "branch-b", entry_id="e3")

        path_e3 = path_to_entry([e1, e2, e3], "e3")
        assert [e.id for e in path_e3] == ["e1", "e3"]

    def test_branch_path_to_left(self):
        e1 = SessionEntry.message(None, TS, "user", "root", entry_id="e1")
        e2 = SessionEntry.message("e1", TS, "assistant", "branch-a", entry_id="e2")
        e3 = SessionEntry.message("e1", TS, "assistant", "branch-b", entry_id="e3")

        path_e2 = path_to_entry([e1, e2, e3], "e2")
        assert [e.id for e in path_e2] == ["e1", "e2"]

    def test_raises_for_unknown_leaf(self):
        e1 = SessionEntry.message(None, TS, "user", "hi", entry_id="e1")
        with pytest.raises(ValueError, match="Unknown leaf_id"):
            path_to_entry([e1], "does_not_exist")

    def test_raises_for_cycle(self):
        # e_a.parent_id -> e_b, e_b.parent_id -> e_a  (no root)
        e_a = SessionEntry(id="e_a", parent_id="e_b", timestamp=TS, kind=KIND_MESSAGE, payload={})
        e_b = SessionEntry(id="e_b", parent_id="e_a", timestamp=TS, kind=KIND_MESSAGE, payload={})
        with pytest.raises(ValueError, match="Cycle detected"):
            path_to_entry([e_a, e_b], "e_a")


# ---------------------------------------------------------------------------
# active_leaf_id
# ---------------------------------------------------------------------------


class TestActiveLeafId:
    def test_returns_leaf_target_when_present(self):
        m1 = SessionEntry.message(None, TS, "user", "hi", entry_id="m1")
        m2 = SessionEntry.message("m1", TS, "assistant", "hello", entry_id="m2")
        lf = SessionEntry.leaf("m2", TS, entry_id_target="m1", entry_id="lf1")

        result = active_leaf_id([m1, m2, lf])
        assert result == "m1"

    def test_returns_last_leaf_target_when_multiple_leaves(self):
        m1 = SessionEntry.message(None, TS, "user", "hi", entry_id="m1")
        m2 = SessionEntry.message("m1", TS, "assistant", "hello", entry_id="m2")
        lf1 = SessionEntry.leaf("m1", TS, entry_id_target="m1", entry_id="lf1")
        lf2 = SessionEntry.leaf("m2", TS, entry_id_target="m2", entry_id="lf2")

        result = active_leaf_id([m1, m2, lf1, lf2])
        assert result == "m2"

    def test_falls_back_to_last_message_id(self):
        m1 = SessionEntry.message(None, TS, "user", "a", entry_id="m1")
        m2 = SessionEntry.message("m1", TS, "assistant", "b", entry_id="m2")
        mc = SessionEntry.model_change("m2", TS, model="claude-3", entry_id="mc1")

        result = active_leaf_id([m1, m2, mc])
        assert result == "m2"

    def test_returns_none_for_empty(self):
        assert active_leaf_id([]) is None

    def test_returns_none_when_no_messages_or_leaves(self):
        info = SessionEntry.info(None, TS, cwd="/tmp", entry_id="inf1")
        assert active_leaf_id([info]) is None


# ---------------------------------------------------------------------------
# reconstruct_messages — linear case
# ---------------------------------------------------------------------------


class TestReconstructMessagesLinear:
    def test_three_messages_in_order(self):
        m1 = SessionEntry.message(None, TS, "user", "msg1", entry_id="m1")
        m2 = SessionEntry.message("m1", TS, "assistant", "msg2", entry_id="m2")
        m3 = SessionEntry.message("m2", TS, "user", "msg3", entry_id="m3")

        result = reconstruct_messages([m1, m2, m3], leaf_id="m3")

        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "msg1"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "msg2"
        assert result[2]["role"] == "user"
        assert result[2]["content"] == "msg3"

    def test_uses_active_leaf_when_leaf_id_is_none(self):
        m1 = SessionEntry.message(None, TS, "user", "hello", entry_id="m1")
        m2 = SessionEntry.message("m1", TS, "assistant", "world", entry_id="m2")

        result = reconstruct_messages([m1, m2])

        assert len(result) == 2
        assert result[1]["content"] == "world"

    def test_returns_empty_for_no_entries(self):
        assert reconstruct_messages([]) == []


# ---------------------------------------------------------------------------
# reconstruct_messages — compaction
# ---------------------------------------------------------------------------


class TestReconstructMessagesCompaction:
    def _build_compacted_chain(self):
        """m1 <- m2 <- m3 <- compaction(replaces=[m1.id, m2.id]) <- m3 remains."""
        m1 = SessionEntry.message(None, TS, "user", "first", entry_id="m1")
        m2 = SessionEntry.message("m1", TS, "assistant", "second", entry_id="m2")
        m3 = SessionEntry.message("m2", TS, "user", "third", entry_id="m3")
        cmp = SessionEntry.compaction(
            parent_id="m3",
            timestamp=TS,
            summary="Earlier chat summarized here.",
            replaces=["m1", "m2"],
            summary_tokens=10,
            entry_id="cmp1",
        )
        # A final message after compaction
        m4 = SessionEntry.message("cmp1", TS, "assistant", "after summary", entry_id="m4")
        return m1, m2, m3, cmp, m4

    def test_compaction_omits_replaced_injects_summary(self):
        m1, m2, m3, cmp, m4 = self._build_compacted_chain()
        result = reconstruct_messages([m1, m2, m3, cmp, m4], leaf_id="m4")

        # m1 and m2 are replaced; compaction synthetic message is injected
        # at the position of the FIRST replaced message (m1); m3 and m4 are kept.
        roles = [r["role"] for r in result]
        contents = [r["content"] for r in result]

        # Expected order: summary (injected at m1's position), m3 (user "third"), m4 (assistant)
        assert len(result) == 3
        assert contents[0].startswith(COMPACTION_PREFIX)  # summary injected at first replaced pos
        assert "Earlier chat summarized here." in contents[0]
        assert contents[1] == "third"  # m3 preserved
        assert contents[2] == "after summary"  # m4 preserved

    def test_summary_content_starts_with_prefix(self):
        m1, m2, m3, cmp, m4 = self._build_compacted_chain()
        result = reconstruct_messages([m1, m2, m3, cmp, m4], leaf_id="m4")

        summary_msg = next(r for r in result if r["content"].startswith(COMPACTION_PREFIX))
        assert summary_msg["role"] == "user"
        assert summary_msg["tool_call_id"] is None
        assert summary_msg["tool_calls"] == []
        assert summary_msg["token_count"] == 10

    def test_m3_intact_after_compaction(self):
        m1, m2, m3, cmp, m4 = self._build_compacted_chain()
        result = reconstruct_messages([m1, m2, m3, cmp, m4], leaf_id="m4")

        # summary is now at result[0]; m3 is at result[1]
        m3_msg = result[1]
        assert m3_msg["content"] == "third"
        assert m3_msg["role"] == "user"


# ---------------------------------------------------------------------------
# reconstruct_messages — branch selection
# ---------------------------------------------------------------------------


class TestReconstructMessagesBranch:
    def test_different_leaves_yield_different_messages(self):
        """
        Root r <- branch-a message a1
              <- branch-b message b1

        Reconstructing a1 must not include b1 and vice-versa.
        """
        root = SessionEntry.message(None, TS, "user", "root msg", entry_id="root")
        a1 = SessionEntry.message("root", TS, "assistant", "branch A reply", entry_id="a1")
        b1 = SessionEntry.message("root", TS, "assistant", "branch B reply", entry_id="b1")

        result_a = reconstruct_messages([root, a1, b1], leaf_id="a1")
        result_b = reconstruct_messages([root, a1, b1], leaf_id="b1")

        contents_a = [r["content"] for r in result_a]
        contents_b = [r["content"] for r in result_b]

        assert "branch A reply" in contents_a
        assert "branch B reply" not in contents_a

        assert "branch B reply" in contents_b
        assert "branch A reply" not in contents_b

        # Both share the root message.
        assert "root msg" in contents_a
        assert "root msg" in contents_b
