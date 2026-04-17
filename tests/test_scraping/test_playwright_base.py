import json
import pytest
from unittest.mock import AsyncMock
from autoso.scraping.playwright_base import PlaywrightScraper


@pytest.mark.asyncio
async def test_get_context_loads_saved_session(tmp_path):
    """If a session file exists it is passed as storage_state to new_context."""
    scraper = PlaywrightScraper("instagram")
    session_file = tmp_path / "instagram_session.json"
    session_data = {
        "cookies": [{"name": "sessionid", "value": "abc123", "domain": ".instagram.com"}]
    }
    session_file.write_text(json.dumps(session_data))
    scraper._session_file = session_file

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=AsyncMock())
    await scraper._get_context(mock_browser)

    call_kwargs = mock_browser.new_context.call_args.kwargs
    assert call_kwargs["storage_state"]["cookies"][0]["name"] == "sessionid"


@pytest.mark.asyncio
async def test_get_context_no_storage_state_when_no_session_file(tmp_path):
    """If no session file exists, storage_state is None."""
    scraper = PlaywrightScraper("facebook")
    scraper._session_file = tmp_path / "facebook_session.json"  # doesn't exist

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=AsyncMock())
    await scraper._get_context(mock_browser)

    call_kwargs = mock_browser.new_context.call_args.kwargs
    assert call_kwargs.get("storage_state") is None


@pytest.mark.asyncio
async def test_save_session_writes_to_file(tmp_path):
    """_save_session writes the context's storage_state to disk."""
    scraper = PlaywrightScraper("instagram")
    scraper._session_file = tmp_path / "instagram_session.json"

    mock_context = AsyncMock()
    mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
    await scraper._save_session(mock_context)

    assert scraper._session_file.exists()
    data = json.loads(scraper._session_file.read_text())
    assert "cookies" in data
