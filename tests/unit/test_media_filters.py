"""Tests for core-media handling and cross-sell exclusion."""
from app.services.media_filters import (
    is_core_media,
    normalize_media_name,
    filter_cross_sell,
)


class TestIsCoreMedia:
    def test_detects_canonical_name(self):
        assert is_core_media("マイナビバイト")

    def test_detects_with_separators(self):
        assert is_core_media("マイナビ バイト")
        assert is_core_media("マイナビ・バイト")

    def test_detects_romaji_alias(self):
        assert is_core_media("Mynavi Baito")

    def test_rejects_other_media(self):
        assert not is_core_media("Indeed")
        assert not is_core_media("エンポケ")
        assert not is_core_media("タウンワーク")

    def test_empty_is_false(self):
        assert not is_core_media("")
        assert not is_core_media(None)  # type: ignore[arg-type]

    def test_custom_core_media(self):
        assert is_core_media("タウンワーク", core_media="タウンワーク")
        assert not is_core_media("マイナビバイト", core_media="タウンワーク")


class TestNormalize:
    def test_nfkc_and_lower(self):
        assert normalize_media_name("ＡＢＣ") == "abc"

    def test_strips_separators(self):
        assert normalize_media_name("a-b_c") == "abc"


class TestFilterCrossSell:
    def test_removes_core_medium_items(self):
        s2 = {
            "cross_sell": [
                {"product_name": "エンポケ", "category": "採用管理"},
                {"product_name": "マイナビバイト プレミアム", "media_name": "マイナビバイト"},
                {"product_name": "応募代行サービス"},
            ]
        }
        out = filter_cross_sell(s2, "マイナビバイト")
        names = [c["product_name"] for c in out["cross_sell"]]
        assert "エンポケ" in names
        assert "応募代行サービス" in names
        assert all("マイナビバイト" not in n for n in names)
        assert out["cross_sell_excluded"] == 1

    def test_no_cross_sell_key_is_noop(self):
        s2 = {"proposals": []}
        assert filter_cross_sell(s2, "マイナビバイト") == {"proposals": []}

    def test_non_dict_passthrough(self):
        assert filter_cross_sell(None, "マイナビバイト") is None  # type: ignore[arg-type]
