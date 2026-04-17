# tests/test_auth.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def authorized_update():
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()
    return update

@pytest.fixture
def unauthorized_update():
    update = MagicMock()
    update.effective_user.id = 99999
    update.message.reply_text = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    return MagicMock()

async def test_authorized_user_passes_through(authorized_update, mock_context):
    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth
        called = []

        @require_auth
        async def handler(update, context):
            called.append(True)

        await handler(authorized_update, mock_context)

    assert called == [True]
    authorized_update.message.reply_text.assert_not_called()

async def test_unauthorized_user_is_rejected(unauthorized_update, mock_context):
    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth
        called = []

        @require_auth
        async def handler(update, context):
            called.append(True)

        await handler(unauthorized_update, mock_context)

    assert called == []
    unauthorized_update.message.reply_text.assert_called_once_with(
        "Unauthorised. Contact the bot administrator to request access."
    )

async def test_handler_return_value_preserved(authorized_update, mock_context):
    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth

        @require_auth
        async def handler(update, context):
            return "result"

        result = await handler(authorized_update, mock_context)

    assert result == "result"


async def test_unauthorized_user_with_no_message_does_not_raise(mock_context):
    """Callback queries have no update.message — must not AttributeError."""
    update = MagicMock()
    update.effective_user.id = 99999
    update.message = None
    update.effective_chat.id = 111

    mock_context.bot = AsyncMock()
    mock_context.bot.send_message = AsyncMock()

    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth
        called = []

        @require_auth
        async def handler(update, context):
            called.append(True)

        await handler(update, mock_context)

    assert called == []
    mock_context.bot.send_message.assert_called_once()
