from __future__ import annotations

from enum import Enum


class PageType(str, Enum):
    FRAMESET_INDEX = "frameset_index"
    TABLE_INDEX = "table_index"
    LIST_INDEX = "list_index"
    BRIDGE_DOWNLOAD_PAGE = "bridge_download_page"
    DOCUMENT_DETAIL_PAGE = "document_detail_page"
    NEWS_LISTING = "news_listing"
    NEWS_ARTICLE_PAGE = "news_article_page"
    GENERIC_INDEX = "generic_index"
    ARTIFACT_HUB = "artifact_hub"
    SESSION_DETAIL_PAGE = "session_detail_page"
    CALENDAR_INDEX = "calendar_index"
    MIXED_INDEX = "mixed_index"
    UNKNOWN = "unknown"
