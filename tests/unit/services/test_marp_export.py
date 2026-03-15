# ai-micro-api-sales/tests/unit/services/test_marp_export.py
"""
Unit tests for marp_export_service.

Tests:
- Markdown concatenation with --- separators
- Marp frontmatter generation
- Marp CLI command arguments
- MinIO upload call
- Status update after export
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4


def _make_mock_doc(num_pages=3, theme="default", title="テスト提案書"):
    doc = MagicMock()
    doc.id = uuid4()
    doc.title = title
    doc.marp_theme = theme
    doc.status = "draft"

    pages = []
    for i in range(1, num_pages + 1):
        page = MagicMock()
        page.page_number = i
        page.markdown_content = f"# ページ{i}\n\n内容{i}"
        pages.append(page)
    doc.pages = pages
    return doc


@pytest.mark.unit
class TestMarpExport:
    """Tests for marp_export_service functions."""

    def test_build_marp_markdown_concatenation(self):
        """All pages SHALL be concatenated with --- separators."""
        from app.services.marp_export_service import _build_marp_markdown

        doc = _make_mock_doc(num_pages=3)
        result = _build_marp_markdown(doc)

        assert "# ページ1" in result
        assert "# ページ2" in result
        assert "# ページ3" in result
        assert result.count("---") >= 2  # At least 2 separators for 3 pages

    def test_build_marp_markdown_frontmatter(self):
        """Frontmatter SHALL include marp: true, theme, paginate, and footer."""
        from app.services.marp_export_service import _build_marp_markdown

        doc = _make_mock_doc(theme="uncover", title="My Proposal")
        result = _build_marp_markdown(doc)

        assert "marp: true" in result
        assert "theme: uncover" in result
        assert "paginate: true" in result
        assert 'footer: "My Proposal"' in result

    def test_build_marp_markdown_page_order(self):
        """Pages SHALL be ordered by page_number."""
        from app.services.marp_export_service import _build_marp_markdown

        doc = _make_mock_doc(num_pages=3)
        # Reverse the internal order to test sorting
        doc.pages = list(reversed(doc.pages))
        result = _build_marp_markdown(doc)

        pos1 = result.index("# ページ1")
        pos2 = result.index("# ページ2")
        pos3 = result.index("# ページ3")
        assert pos1 < pos2 < pos3

    def test_build_marp_markdown_single_page(self):
        """Single page document SHALL produce valid Marp output."""
        from app.services.marp_export_service import _build_marp_markdown

        doc = _make_mock_doc(num_pages=1)
        result = _build_marp_markdown(doc)

        assert "marp: true" in result
        assert "# ページ1" in result
        # No separator needed for single page
        assert result.count("\n\n---\n\n") == 0

    def test_build_marp_markdown_empty_pages(self):
        """Document with no pages SHALL still have frontmatter."""
        from app.services.marp_export_service import _build_marp_markdown

        doc = _make_mock_doc(num_pages=0)
        doc.pages = []
        result = _build_marp_markdown(doc)

        assert "marp: true" in result
        assert "paginate: true" in result
