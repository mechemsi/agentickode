# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.git.url_parser."""

import pytest

from backend.services.git.url_parser import ParsedGitUrl, parse_git_url

# ---------------------------------------------------------------------------
# SSH URL tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        # GitHub SSH with .git
        (
            "git@github.com:owner/repo.git",
            ParsedGitUrl(provider="github", owner="owner", repo="repo", host="github.com"),
        ),
        # GitHub SSH without .git
        (
            "git@github.com:owner/repo",
            ParsedGitUrl(provider="github", owner="owner", repo="repo", host="github.com"),
        ),
        # GitLab SSH with .git
        (
            "git@gitlab.com:mygroup/myproject.git",
            ParsedGitUrl(provider="gitlab", owner="mygroup", repo="myproject", host="gitlab.com"),
        ),
        # GitLab SSH without .git
        (
            "git@gitlab.com:mygroup/myproject",
            ParsedGitUrl(provider="gitlab", owner="mygroup", repo="myproject", host="gitlab.com"),
        ),
        # Bitbucket SSH with .git
        (
            "git@bitbucket.org:atlassian/python-bitbucket.git",
            ParsedGitUrl(
                provider="bitbucket",
                owner="atlassian",
                repo="python-bitbucket",
                host="bitbucket.org",
            ),
        ),
        # Bitbucket SSH without .git
        (
            "git@bitbucket.org:atlassian/python-bitbucket",
            ParsedGitUrl(
                provider="bitbucket",
                owner="atlassian",
                repo="python-bitbucket",
                host="bitbucket.org",
            ),
        ),
        # Custom / self-hosted SSH — unknown provider
        (
            "git@git.example.com:devops/infra.git",
            ParsedGitUrl(
                provider="unknown",
                owner="devops",
                repo="infra",
                host="git.example.com",
            ),
        ),
        (
            "git@git.example.com:devops/infra",
            ParsedGitUrl(
                provider="unknown",
                owner="devops",
                repo="infra",
                host="git.example.com",
            ),
        ),
    ],
)
def test_ssh_urls(url: str, expected: ParsedGitUrl) -> None:
    assert parse_git_url(url) == expected


# ---------------------------------------------------------------------------
# HTTPS URL tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        # GitHub HTTPS with .git
        (
            "https://github.com/owner/repo.git",
            ParsedGitUrl(provider="github", owner="owner", repo="repo", host="github.com"),
        ),
        # GitHub HTTPS without .git
        (
            "https://github.com/owner/repo",
            ParsedGitUrl(provider="github", owner="owner", repo="repo", host="github.com"),
        ),
        # GitLab HTTPS with .git
        (
            "https://gitlab.com/mygroup/myproject.git",
            ParsedGitUrl(provider="gitlab", owner="mygroup", repo="myproject", host="gitlab.com"),
        ),
        # GitLab HTTPS without .git
        (
            "https://gitlab.com/mygroup/myproject",
            ParsedGitUrl(provider="gitlab", owner="mygroup", repo="myproject", host="gitlab.com"),
        ),
        # Bitbucket HTTPS with .git
        (
            "https://bitbucket.org/atlassian/python-bitbucket.git",
            ParsedGitUrl(
                provider="bitbucket",
                owner="atlassian",
                repo="python-bitbucket",
                host="bitbucket.org",
            ),
        ),
        # Bitbucket HTTPS without .git
        (
            "https://bitbucket.org/atlassian/python-bitbucket",
            ParsedGitUrl(
                provider="bitbucket",
                owner="atlassian",
                repo="python-bitbucket",
                host="bitbucket.org",
            ),
        ),
        # Custom host HTTPS — unknown provider
        (
            "https://git.example.com/devops/infra.git",
            ParsedGitUrl(
                provider="unknown",
                owner="devops",
                repo="infra",
                host="git.example.com",
            ),
        ),
        (
            "https://git.example.com/devops/infra",
            ParsedGitUrl(
                provider="unknown",
                owner="devops",
                repo="infra",
                host="git.example.com",
            ),
        ),
    ],
)
def test_https_urls(url: str, expected: ParsedGitUrl) -> None:
    assert parse_git_url(url) == expected


# ---------------------------------------------------------------------------
# HTTP URL tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "http://github.com/owner/repo",
            ParsedGitUrl(provider="github", owner="owner", repo="repo", host="github.com"),
        ),
        (
            "http://git.internal.corp/team/project",
            ParsedGitUrl(
                provider="unknown",
                owner="team",
                repo="project",
                host="git.internal.corp",
            ),
        ),
    ],
)
def test_http_urls(url: str, expected: ParsedGitUrl) -> None:
    assert parse_git_url(url) == expected


# ---------------------------------------------------------------------------
# .git suffix stripping
# ---------------------------------------------------------------------------


def test_git_suffix_stripped_ssh() -> None:
    result = parse_git_url("git@github.com:owner/repo.git")
    assert result.repo == "repo"
    assert not result.repo.endswith(".git")


def test_git_suffix_stripped_https() -> None:
    result = parse_git_url("https://github.com/owner/repo.git")
    assert result.repo == "repo"
    assert not result.repo.endswith(".git")


# ---------------------------------------------------------------------------
# Unknown host → provider = "unknown"
# ---------------------------------------------------------------------------


def test_unknown_host_ssh() -> None:
    result = parse_git_url("git@selfhosted.example.org:team/service.git")
    assert result.provider == "unknown"
    assert result.host == "selfhosted.example.org"


def test_unknown_host_https() -> None:
    result = parse_git_url("https://selfhosted.example.org/team/service")
    assert result.provider == "unknown"
    assert result.host == "selfhosted.example.org"


# ---------------------------------------------------------------------------
# Invalid URLs → ValueError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_url",
    [
        "",  # empty string
        "   ",  # whitespace only
        "not-a-url",  # no scheme, no SSH format
        "ftp://github.com/owner/repo",  # unsupported scheme
        "https://github.com/owner",  # missing repo segment
        "https://github.com/",  # missing owner and repo
        "https://github.com",  # no path at all
        "git@github.com:owner",  # SSH missing /repo
        "git@github.com:",  # SSH missing owner and repo
    ],
)
def test_invalid_urls_raise_value_error(bad_url: str) -> None:
    with pytest.raises(ValueError):
        parse_git_url(bad_url)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_trailing_slash_https() -> None:
    result = parse_git_url("https://github.com/owner/repo/")
    assert result.owner == "owner"
    assert result.repo == "repo"


def test_leading_whitespace_stripped() -> None:
    result = parse_git_url("  git@github.com:owner/repo.git  ")
    assert result.owner == "owner"
    assert result.repo == "repo"


def test_host_preserved_in_result() -> None:
    result = parse_git_url("git@github.com:owner/repo.git")
    assert result.host == "github.com"


def test_https_host_preserved_in_result() -> None:
    result = parse_git_url("https://gitlab.com/mygroup/myproject")
    assert result.host == "gitlab.com"


def test_repo_name_with_hyphens_and_underscores() -> None:
    result = parse_git_url("git@github.com:my-org/my_cool-repo.git")
    assert result.owner == "my-org"
    assert result.repo == "my_cool-repo"