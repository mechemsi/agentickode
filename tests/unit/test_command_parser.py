# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from backend.services.messaging.command_parser import parse_command


class TestParseCommand:
    def test_run_command(self):
        cmd = parse_command("run myproject Fix the login bug")
        assert cmd.action == "run"
        assert cmd.project == "myproject"
        assert cmd.args["task"] == "Fix the login bug"

    def test_run_without_task(self):
        cmd = parse_command("run myproject")
        assert cmd.action == "run"
        assert cmd.project == "myproject"
        assert cmd.args["task"] == ""

    def test_status_command(self):
        cmd = parse_command("status 42")
        assert cmd.action == "status"
        assert cmd.args["run_id"] == "42"

    def test_approve_command(self):
        cmd = parse_command("approve 42")
        assert cmd.action == "approve"
        assert cmd.args["run_id"] == "42"

    def test_reject_with_reason(self):
        cmd = parse_command("reject 42 bad approach")
        assert cmd.action == "reject"
        assert cmd.args["run_id"] == "42"
        assert cmd.args["reason"] == "bad approach"

    def test_list_command(self):
        cmd = parse_command("list")
        assert cmd.action == "list"

    def test_help_command(self):
        cmd = parse_command("help")
        assert cmd.action == "help"

    def test_talk_command(self):
        cmd = parse_command("talk sess-123 What did you change?")
        assert cmd.action == "talk"
        assert cmd.args["session_id"] == "sess-123"
        assert cmd.args["message"] == "What did you change?"

    def test_empty_input(self):
        cmd = parse_command("")
        assert cmd.action == "help"

    def test_strips_bot_mention(self):
        cmd = parse_command("<@U12345> run myproject Fix bug")
        assert cmd.action == "run"
        assert cmd.project == "myproject"

    def test_strips_slash_command_prefix(self):
        cmd = parse_command("/agentickode run myproject Fix bug")
        assert cmd.action == "run"
        assert cmd.project == "myproject"

    def test_unknown_command_returns_help(self):
        cmd = parse_command("foobar something")
        assert cmd.action == "help"

    def test_case_insensitive_action(self):
        cmd = parse_command("RUN myproject fix things")
        assert cmd.action == "run"

    def test_raw_text_preserved(self):
        cmd = parse_command("run myproject do stuff")
        assert cmd.raw_text == "run myproject do stuff"
