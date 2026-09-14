"""Row-addressed backfill for durable API/canonical text divergence.\n\nKissne request-local context is deliberately excluded from api_content.\nThe remaining protection covers independently-produced API text, such as a\nvoice prefix, when an early flush or in-place compaction has already inserted\nthe clean canonical row. Row ids prevent repeated prompts from updating the\nwrong turn (NousResearch/hermes-agent#102194).\n"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from agent.session_persistence import SessionPersistenceMixin
from hermes_state import SessionDB
from tests.agent.test_api_content_sidecar import _FakeAgent, _build


class TestSetMessageApiContent:
    """The store primitive: addressed by row id, guarded on the rest."""

    def _open(self, tmp_path):
        db = SessionDB(db_path=tmp_path / "state.db")
        db.create_session("s1", source="cli")
        return db

    def test_older_identical_row_is_untouched(self, tmp_path):
        """Two user turns with the same text — the repeated-"ok" shape.

        Addressing the row makes the older turn's sidecar unreachable; the
        positional helper cannot tell them apart (asserted on the same DB).
        """
        db = self._open(tmp_path)
        try:
            db.append_message("s1", "user", content="ok", api_content="ok\n\nTURN-1")
            db.append_message("s1", "assistant", content="reply")
            db.append_message("s1", "user", content="ok")
            rows = db.get_messages("s1")
            turn_1_id, turn_2_id = rows[0]["id"], rows[2]["id"]

            assert db.set_message_api_content("s1", turn_2_id, "ok", "ok\n\nTURN-2") == 1
            rows = {r["id"]: r for r in db.get_messages("s1")}
            assert rows[turn_1_id]["api_content"] == "ok\n\nTURN-1"
            assert rows[turn_2_id]["api_content"] == "ok\n\nTURN-2"

        finally:
            db.close()

    def test_guards_refuse_wrong_session_or_mismatched_content_or_archived_row(self, tmp_path):
        db = self._open(tmp_path)
        try:
            db.create_session("s2", source="cli")
            db.append_message("s1", "user", content="hello")
            row_id = db.get_messages("s1")[0]["id"]

            assert db.set_message_api_content("s2", row_id, "hello", "x") == 0
            assert db.set_message_api_content("s1", row_id, "other", "x") == 0
            assert db.set_message_api_content("s1", row_id + 999, "hello", "x") == 0
            assert db.get_messages("s1")[0]["api_content"] is None

            # Archived by compaction: active = 0, so the row is off limits.
            db.archive_and_compact("s1", [{"role": "user", "content": "hello"}])
            assert db.set_message_api_content("s1", row_id, "hello", "x") == 0
        finally:
            db.close()


class TestEphemeralBackfillRetired:
    """Plugin/runtime context must not enter the durable sidecar."""

    def test_plugin_context_does_not_stamp_or_backfill(self):
        agent = _FakeAgent()
        agent._session_db = MagicMock()
        with patch(
            "hermes_cli.plugins.invoke_hook",
            return_value=[{"context": "PLUGIN-CTX"}],
        ):
            ctx = _build(agent)

        turn_msg = ctx.messages[ctx.current_turn_user_idx]
        assert "api_content" not in turn_msg
        assert ctx.plugin_user_context == "PLUGIN-CTX"
        agent._session_db.set_message_api_content.assert_not_called()
        agent._session_db.set_latest_user_api_content.assert_not_called()


class _RealPersistenceAgent(SessionPersistenceMixin, _FakeAgent):
    """Stand-in agent with the real SessionPersistenceMixin flush implementation."""

    def __init__(self, db=None, sid="s1"):
        _FakeAgent.__init__(self)
        self._session_db = db
        self.session_id = sid
        self._session_db_created = True
        self._flushed_db_message_ids = set()
        self._last_flushed_db_idx = 0



class TestRealEarlyFlushAndOverrideLifecycle:
    """End-to-end tests for retired ephemeral and retained API-only backfill."""

    def test_real_close_flush_does_not_backfill_plugin_context(self, tmp_path):
        path = tmp_path / "state.db"
        db = SessionDB(db_path=path)
        sid = "sess-real-flush"
        db.create_session(sid, source="cli")
        try:
            agent = _RealPersistenceAgent(db, sid)
            staged = {"role": "user", "content": "hello"}
            agent._pending_cli_user_message = staged

            assert agent._flush_messages_to_session_db([staged], None) is True
            assert isinstance(staged.get("_row_id"), int)
            assert db.get_messages(sid)[-1]["api_content"] is None

            with patch(
                "hermes_cli.plugins.invoke_hook",
                return_value=[{"context": "PLUGIN-CTX"}],
            ):
                ctx = _build(agent)

            turn_msg = ctx.messages[ctx.current_turn_user_idx]
            assert "api_content" not in turn_msg
            assert ctx.plugin_user_context == "PLUGIN-CTX"
            assert db.get_messages(sid)[-1]["api_content"] is None
        finally:
            db.close()

    def test_pre_flushed_api_only_turn_preserves_sidecar(self, tmp_path):
        """A voice/API prefix remains replayable even though Kissne context does not."""
        path = tmp_path / "state.db"
        db = SessionDB(db_path=path)
        sid = "sess-api-only-no-inj"
        db.create_session(sid, source="cli")
        try:
            agent = _RealPersistenceAgent(db, sid)
            clean_text = "hello"
            api_text = "[voice] hello"
            staged = {"role": "user", "content": clean_text}
            agent._pending_cli_user_message = staged
            agent._flush_messages_to_session_db([staged], None)
            assert staged.get("_row_id") is not None

            with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
                ctx = _build(
                    agent,
                    user_message=api_text,
                    persist_user_message=clean_text,
                )

            turn_msg = ctx.messages[ctx.current_turn_user_idx]
            assert turn_msg["content"] == api_text
            assert turn_msg["api_content"] == api_text

            db_rows = db.get_messages(sid)
            assert len(db_rows) == 1
            assert db_rows[0]["content"] == clean_text
            assert db_rows[0]["api_content"] == api_text

            conv = db.get_messages_as_conversation(sid)
            assert conv[0]["content"] == clean_text
            assert conv[0]["api_content"] == api_text
            from agent.turn_context import substitute_api_content
            substitute_api_content(conv[0])
            assert conv[0]["content"] == api_text
        finally:
            db.close()

    def test_repeated_prompt_uses_row_addressed_api_only_backfill(self, tmp_path):
        path = tmp_path / "state.db"
        db = SessionDB(db_path=path)
        sid = "sess-repeated-ok"
        db.create_session(sid, source="cli")
        try:
            db.append_message(
                sid, "user", content="ok", api_content="[voice-1] ok"
            )
            db.append_message(sid, "assistant", content="acknowledged")
            turn_1 = db.get_messages(sid)[0]

            staged_turn_2 = {"role": "user", "content": "ok"}
            agent = _RealPersistenceAgent(db, sid)
            agent._pending_cli_user_message = staged_turn_2
            agent._flush_messages_to_session_db([staged_turn_2], None)
            turn_2 = db.get_messages(sid)[2]
            assert turn_2["id"] != turn_1["id"]
            assert turn_2["api_content"] is None

            with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
                _build(
                    agent,
                    user_message="[voice-2] ok",
                    persist_user_message="ok",
                )

            rows = {item["id"]: item for item in db.get_messages(sid)}
            assert rows[turn_1["id"]]["api_content"] == "[voice-1] ok"
            assert rows[turn_2["id"]]["api_content"] == "[voice-2] ok"
        finally:
            db.close()


