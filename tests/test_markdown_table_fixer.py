"""Tests for markdown_table_fixer utility."""

from app.utils.markdown_table_fixer import fix_markdown_tables


class TestFixMarkdownTables:
    """Test cases for fix_markdown_tables."""

    def test_valid_table_unchanged(self):
        md = (
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| A | 1 |\n"
            "| B | 2 |"
        )
        result = fix_markdown_tables(md)
        assert "| --- | --- |" in result
        assert result.count("\n") == md.count("\n")

    def test_missing_separator_row(self):
        md = (
            "| Name | Value |\n"
            "| A | 1 |\n"
            "| B | 2 |"
        )
        result = fix_markdown_tables(md)
        lines = result.split("\n")
        assert lines[1] == "| --- | --- |"
        assert len(lines) == 4  # header + separator + 2 data rows

    def test_inconsistent_column_count(self):
        md = (
            "| A | B | C |\n"
            "| --- | --- |\n"
            "| 1 | 2 |"
        )
        result = fix_markdown_tables(md)
        lines = result.split("\n")
        # All rows should have 3 columns
        for line in lines:
            assert line.count("|") == 4  # 3 cols = 4 pipes

    def test_missing_outer_pipes(self):
        md = (
            "Name | Value\n"
            "A | 1\n"
            "B | 2"
        )
        result = fix_markdown_tables(md)
        lines = result.split("\n")
        for line in lines:
            assert line.strip().startswith("|")
            assert line.strip().endswith("|")
        # Separator should be inserted
        assert "---" in lines[1]

    def test_surrounding_text_preserved(self):
        md = (
            "# Title\n"
            "\n"
            "Some text before.\n"
            "\n"
            "| Col1 | Col2 |\n"
            "| A | B |\n"
            "\n"
            "Text after."
        )
        result = fix_markdown_tables(md)
        assert result.startswith("# Title")
        assert result.endswith("Text after.")
        assert "| --- | --- |" in result

    def test_multiple_tables(self):
        md = (
            "| H1 | H2 |\n"
            "| a | b |\n"
            "\n"
            "gap\n"
            "\n"
            "| X | Y |\n"
            "| 1 | 2 |"
        )
        result = fix_markdown_tables(md)
        # Both tables should have separator rows
        assert result.count("| --- | --- |") == 2

    def test_empty_string(self):
        assert fix_markdown_tables("") == ""

    def test_no_tables(self):
        md = "# Hello\n\nJust text."
        assert fix_markdown_tables(md) == md

    def test_table_with_extra_column_in_body(self):
        """Body row has more columns than header."""
        md = (
            "| A | B |\n"
            "| --- | --- |\n"
            "| 1 | 2 | 3 |"
        )
        result = fix_markdown_tables(md)
        lines = result.split("\n")
        # Column count should be normalized to max (3)
        assert lines[0].count("|") == 4  # 3 cols
        assert lines[1].count("|") == 4

    def test_already_correct_table_idempotent(self):
        md = (
            "| A | B | C |\n"
            "| --- | --- | --- |\n"
            "| 1 | 2 | 3 |\n"
            "| 4 | 5 | 6 |"
        )
        result = fix_markdown_tables(md)
        result2 = fix_markdown_tables(result)
        assert result == result2

    def test_single_column_table(self):
        md = (
            "| Item |\n"
            "| A |\n"
            "| B |"
        )
        result = fix_markdown_tables(md)
        assert "| --- |" in result
