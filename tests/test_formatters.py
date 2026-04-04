"""Tests for mastodon_blade_mcp.formatters -- HTML stripping, compact output."""

from __future__ import annotations

from mastodon_blade_mcp.formatters import (
    format_account,
    format_account_list,
    format_context,
    format_conversations,
    format_filters,
    format_instance_info,
    format_lists,
    format_notification,
    format_notifications,
    format_relationships,
    format_search_results,
    format_status,
    format_timeline,
    format_trending_links,
    format_trending_tags,
    format_verify_credentials,
    strip_html,
    truncate,
)
from tests.conftest import (
    make_account,
    make_conversation,
    make_filter_entry,
    make_list_entry,
    make_notification,
    make_relationship,
    make_status,
    make_trending_tag,
)


class TestStripHtml:
    def test_basic_tags(self) -> None:
        assert strip_html("<p>Hello <strong>world</strong></p>") == "Hello world"

    def test_br_tags(self) -> None:
        result = strip_html("line1<br/>line2<br>line3")
        assert "line1\nline2\nline3" == result

    def test_paragraph_tags(self) -> None:
        result = strip_html("<p>First para</p><p>Second para</p>")
        assert "First para" in result
        assert "Second para" in result

    def test_html_entities(self) -> None:
        assert strip_html("&amp; &lt; &gt; &quot;") == '& < > "'

    def test_empty_string(self) -> None:
        assert strip_html("") == ""

    def test_none_safe(self) -> None:
        assert strip_html("") == ""

    def test_link_tags(self) -> None:
        result = strip_html('<a href="https://example.com">click</a>')
        assert result == "click"
        assert "href" not in result


class TestTruncate:
    def test_short_string(self) -> None:
        assert truncate("hello", 10) == "hello"

    def test_exact_length(self) -> None:
        assert truncate("hello", 5) == "hello"

    def test_long_string(self) -> None:
        result = truncate("a" * 400, 300)
        assert len(result) <= 303  # 300 + "..."
        assert result.endswith("...")

    def test_empty_string(self) -> None:
        assert truncate("", 10) == ""


class TestFormatStatus:
    def test_basic_status(self) -> None:
        status = make_status()
        result = format_status(status)
        assert "109876543210" in result
        assert "@user@mastodon.social" in result
        assert "Hello world!" in result
        assert "public" in result
        assert "fav=5" in result
        assert "boost=2" in result
        assert "reply=1" in result

    def test_zero_counts_omitted(self) -> None:
        status = make_status(favourites_count=0, reblogs_count=0, replies_count=0)
        result = format_status(status)
        assert "fav=" not in result
        assert "boost=" not in result
        assert "reply=" not in result

    def test_spoiler_text(self) -> None:
        status = make_status(spoiler_text="Spoiler ahead")
        result = format_status(status)
        assert "CW: Spoiler ahead" in result

    def test_media_indicator(self) -> None:
        status = make_status(media_attachments=[{"type": "image"}, {"type": "video"}])
        result = format_status(status)
        assert "media=image,video" in result

    def test_reblog_indicator(self) -> None:
        original = make_status(status_id="original-1")
        status = make_status(reblog=original)
        result = format_status(status)
        assert "reblog_of=original-1" in result

    def test_html_stripped(self) -> None:
        status = make_status(content="<p>Hello <strong>world</strong></p>")
        result = format_status(status)
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "Hello world" in result


class TestFormatTimeline:
    def test_empty(self) -> None:
        assert "(no statuses)" in format_timeline([])

    def test_multiple(self) -> None:
        statuses = [make_status(status_id="1"), make_status(status_id="2")]
        result = format_timeline(statuses)
        lines = result.strip().split("\n")
        assert len(lines) == 2


class TestFormatAccount:
    def test_basic_account(self) -> None:
        account = make_account()
        result = format_account(account)
        assert "@user@mastodon.social" in result
        assert "Test User" in result
        assert "followers=100" in result
        assert "following=50" in result
        assert "statuses=200" in result

    def test_bot_flag(self) -> None:
        account = make_account(bot=True)
        result = format_account(account)
        assert "BOT" in result

    def test_locked_flag(self) -> None:
        account = make_account(locked=True)
        result = format_account(account)
        assert "LOCKED" in result


class TestFormatAccountList:
    def test_empty(self) -> None:
        assert "(no accounts)" in format_account_list([])


class TestFormatNotification:
    def test_mention(self) -> None:
        notif = make_notification()
        result = format_notification(notif)
        assert "mention" in result
        assert "@other@mastodon.social" in result
        assert "status=" in result

    def test_follow(self) -> None:
        notif = make_notification(notif_type="follow", status_id=None, content="")
        result = format_notification(notif)
        assert "follow" in result
        assert "status=" not in result


class TestFormatNotifications:
    def test_empty(self) -> None:
        assert "(no notifications)" in format_notifications([])


class TestFormatSearchResults:
    def test_with_accounts_and_statuses(self) -> None:
        results = {
            "accounts": [make_account()],
            "statuses": [make_status()],
            "hashtags": [{"name": "python", "url": "https://mastodon.social/tags/python", "history": []}],
        }
        output = format_search_results(results)
        assert "## Accounts" in output
        assert "## Statuses" in output
        assert "## Hashtags" in output
        assert "#python" in output

    def test_empty(self) -> None:
        result = format_search_results({"accounts": [], "statuses": [], "hashtags": []})
        assert "(no results)" in result


class TestFormatRelationships:
    def test_following(self) -> None:
        rel = make_relationship(following=True, followed_by=True)
        result = format_relationships([rel])
        assert "following" in result
        assert "followed_by" in result

    def test_blocking(self) -> None:
        rel = make_relationship(blocking=True, following=False)
        result = format_relationships([rel])
        assert "blocking" in result

    def test_empty(self) -> None:
        assert "(no relationships)" in format_relationships([])


class TestFormatConversations:
    def test_basic(self) -> None:
        conv = make_conversation()
        result = format_conversations([conv])
        assert "conv-1" in result
        assert "@friend@mastodon.social" in result

    def test_unread(self) -> None:
        conv = make_conversation(unread=True)
        result = format_conversations([conv])
        assert "UNREAD" in result

    def test_empty(self) -> None:
        assert "(no conversations)" in format_conversations([])


class TestFormatLists:
    def test_basic(self) -> None:
        lst = make_list_entry()
        result = format_lists([lst])
        assert "list-1" in result
        assert "Tech News" in result
        assert "replies=list" in result

    def test_empty(self) -> None:
        assert "(no lists)" in format_lists([])


class TestFormatFilters:
    def test_basic(self) -> None:
        f = make_filter_entry()
        result = format_filters([f])
        assert "filter-1" in result
        assert "Spoilers" in result
        assert "context=home,public" in result
        assert "action=warn" in result
        assert "spoiler" in result

    def test_empty(self) -> None:
        assert "(no filters)" in format_filters([])


class TestFormatTrendingTags:
    def test_basic(self) -> None:
        tag = make_trending_tag()
        result = format_trending_tags([tag])
        assert "#python" in result
        assert "uses_today=42" in result
        assert "accounts_today=15" in result

    def test_empty(self) -> None:
        assert "(no trending tags)" in format_trending_tags([])


class TestFormatTrendingLinks:
    def test_empty(self) -> None:
        assert "(no trending links)" in format_trending_links([])

    def test_basic(self) -> None:
        link = {
            "title": "Cool Article",
            "url": "https://example.com/article",
            "description": "An interesting article",
            "history": [{"uses": "10", "accounts": "5"}],
        }
        result = format_trending_links([link])
        assert "Cool Article" in result
        assert "uses_today=10" in result


class TestFormatInstanceInfo:
    def test_basic(self) -> None:
        info = {
            "title": "Mastodon Social",
            "version": "4.2.0",
            "domain": "mastodon.social",
            "stats": {"user_count": 1000, "status_count": 50000, "domain_count": 300},
        }
        result = format_instance_info(info, True, "rate_limit=290/300 reset_in=180s")
        assert "Mastodon Social" in result
        assert "v4.2.0" in result
        assert "write_gate=enabled" in result
        assert "rate_limit=" in result

    def test_write_disabled(self) -> None:
        result = format_instance_info({"title": "Test"}, False, "")
        assert "write_gate=disabled" in result


class TestFormatVerifyCredentials:
    def test_basic(self) -> None:
        account = make_account()
        result = format_verify_credentials(account)
        assert "@user@mastodon.social" in result
        assert "followers=100" in result


class TestFormatContext:
    def test_with_thread(self) -> None:
        context = {
            "ancestors": [make_status(status_id="anc-1")],
            "descendants": [make_status(status_id="desc-1"), make_status(status_id="desc-2")],
        }
        result = format_context(context)
        assert "## Ancestors (1)" in result
        assert "## Descendants (2)" in result
        assert "anc-1" in result
        assert "desc-1" in result

    def test_empty_context(self) -> None:
        result = format_context({"ancestors": [], "descendants": []})
        assert "(no thread context)" in result
