"""Core-media handling and cross-sell exclusion for the proposal pipeline.

PoC requirement: proposals are centered on the core advertising medium
(default: マイナビバイト). Cross-sell suggestions (additional media /
peripheral products) MUST NOT include the core medium itself — cross-sell
must be media *other than* the core medium.

Enforcement is done in two layers:
1. Prompt rule (see pipeline_prompts.STAGE2_SYSTEM_PROMPT).
2. Deterministic post-processing here, so it holds even if the LLM ignores
   the rule or uses表記ゆれ (spelling variants).
"""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

DEFAULT_CORE_MEDIA = "マイナビバイト"

# 表記ゆれ吸収: normalized core-media aliases all map to the canonical key.
# Keys are already normalized via normalize_media_name().
_CORE_MEDIA_ALIASES = {
    "マイナビバイト",
    "マイナビバイト",  # decomposed dakuten safety
    "mynavibaito",
    "mynavibyte",
    "マイナビアルバイト",
}


def normalize_media_name(name: str) -> str:
    """Normalize a media/product name for robust comparison.

    - NFKC (full-width→half-width, compatibility)
    - lower-case
    - strip whitespace and common separators
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name))
    s = s.lower()
    s = re.sub(r"[\s\-_・/（）()\[\]【】]", "", s)
    return s


def is_core_media(name: str, core_media: str = DEFAULT_CORE_MEDIA) -> bool:
    """Return True if the given media/product name refers to the core medium."""
    n = normalize_media_name(name)
    if not n:
        return False
    core_n = normalize_media_name(core_media)
    aliases = {core_n}
    # Apply the known 表記ゆれ aliases only when the configured core medium
    # itself is マイナビバイト (the alias set is specific to that medium).
    if core_n in {normalize_media_name(a) for a in _CORE_MEDIA_ALIASES}:
        aliases |= {normalize_media_name(a) for a in _CORE_MEDIA_ALIASES}
    # exact or substring match against any alias
    return any(alias and (alias in n or n in alias) for alias in aliases)


def filter_cross_sell(stage2_output: dict, core_media: str = DEFAULT_CORE_MEDIA) -> dict:
    """Remove cross_sell items that reference the core medium.

    Mutates and returns stage2_output. A `cross_sell_excluded` count is added
    to the output for transparency (no silent truncation).
    """
    if not isinstance(stage2_output, dict):
        return stage2_output
    items = stage2_output.get("cross_sell")
    if not isinstance(items, list):
        return stage2_output

    kept: list = []
    excluded = 0
    for item in items:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        # Check the fields that may carry a medium/product name.
        candidates = [
            item.get("media_name", ""),
            item.get("product_name", ""),
            item.get("category", ""),
        ]
        if any(is_core_media(c, core_media) for c in candidates):
            excluded += 1
            logger.info(
                "Cross-sell excluded (core medium %s): %s",
                core_media, item.get("product_name") or item.get("media_name"),
            )
            continue
        kept.append(item)

    stage2_output["cross_sell"] = kept
    if excluded:
        stage2_output["cross_sell_excluded"] = excluded
    return stage2_output
