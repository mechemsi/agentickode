# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for the notification dispatcher event routing."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.notifications.dispatcher import _EVENT_MAP, NotificationDispatcher


class TestNotificationDispatcher:
    async def test_dispatch_sends_to_matching_channels(self):
        """Channels whose events list includes the event type receive the notification."""
        ch_match = MagicMock()
        ch_match.name = "tg-alerts"
        ch_match.channel_type = "telegram"
        ch_match.config = {"bot_token": "x", "chat_id": "y"}
        ch_match.events = ["run_completed"]

        ch_skip = MagicMock()
        ch_skip.name = "slack-deploys"
        ch_skip.channel_type = "slack"
        ch_skip.config = {"webhook_url": "https://test"}
        ch_skip.events = ["run_started"]

        mock_repo_cls = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.list_enabled.return_value = [ch_match, ch_skip]
        mock_repo_cls.return_value = mock_repo

        mock_service_cls = MagicMock()
        mock_service = AsyncMock()
        mock_service_cls.return_value = mock_service

        dispatcher = NotificationDispatcher()

        with (
            patch("backend.services.notifications.dispatcher.async_session") as mock_session_ctx,
            patch(
                "backend.services.notifications.dispatcher.NotificationChannelRepository",
                mock_repo_cls,
            ),
            patch(
                "backend.services.notifications.dispatcher.NotificationService", mock_service_cls
            ),
            patch(
                "backend.services.notifications.dispatcher.get_http_client",
                return_value=AsyncMock(),
            ),
        ):
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatcher._dispatch(
                "run_completed",
                {
                    "run_id": 1,
                    "project_id": "proj",
                    "title": "Test",
                },
            )

        # Should have sent to ch_match only
        mock_service.send.assert_called_once()
        sent_channel = mock_service.send.call_args[0][0]
        assert sent_channel.name == "tg-alerts"

    async def test_dispatch_skips_when_no_matching_channels(self):
        """No channels match the event — no sends."""
        ch = MagicMock()
        ch.name = "tg"
        ch.channel_type = "telegram"
        ch.config = {}
        ch.events = ["run_failed"]

        mock_repo_cls = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.list_enabled.return_value = [ch]
        mock_repo_cls.return_value = mock_repo

        mock_service_cls = MagicMock()
        mock_service = AsyncMock()
        mock_service_cls.return_value = mock_service

        dispatcher = NotificationDispatcher()

        with (
            patch("backend.services.notifications.dispatcher.async_session") as mock_session_ctx,
            patch(
                "backend.services.notifications.dispatcher.NotificationChannelRepository",
                mock_repo_cls,
            ),
            patch(
                "backend.services.notifications.dispatcher.NotificationService", mock_service_cls
            ),
            patch(
                "backend.services.notifications.dispatcher.get_http_client",
                return_value=AsyncMock(),
            ),
        ):
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatcher._dispatch(
                "run_started",
                {
                    "run_id": 1,
                    "project_id": "proj",
                },
            )

        mock_service.send.assert_not_called()

    def test_event_map_includes_plan_review(self):
        assert "plan_review_requested" in _EVENT_MAP

    def test_event_map_includes_cost_threshold(self):
        assert "cost_threshold_exceeded" in _EVENT_MAP

    async def test_send_safe_logs_error_on_failure(self):
        """_send_safe catches exceptions and doesn't propagate."""
        mock_service = AsyncMock()
        mock_service.send.side_effect = Exception("network error")

        ch = MagicMock()
        ch.name = "broken"
        ch.channel_type = "webhook"

        dispatcher = NotificationDispatcher()
        # Should not raise
        await dispatcher._send_safe(mock_service, ch, "test msg")