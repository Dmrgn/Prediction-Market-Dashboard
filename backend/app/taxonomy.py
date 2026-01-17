"""
Unified Market Taxonomy

Maps source-specific tags/categories to normalized sectors for consistent filtering.
"""

SECTORS = ["Sports", "Politics", "Crypto", "Economics", "Tech", "Entertainment", "Science", "Other"]

# Polymarket tag slug → Sector mapping
PM_TAG_TO_SECTOR = {
    # Sports
    "sports": "Sports",
    
    # Politics
    "politics": "Politics",
    "u.s. politics": "Politics",
    "world": "Politics",
    "election": "Politics",
    "trump": "Politics",
    "biden": "Politics",
    
    # Crypto
    "crypto": "Crypto",
    "bitcoin": "Crypto",
    "ethereum": "Crypto",
    "defi": "Crypto",
    
    # Economics/Finance
    "economy": "Economics",
    "finance": "Economics",
    "stocks": "Economics",
    "business": "Economics",
    "ipos": "Economics",
    "gdp": "Economics",
    
    # Tech
    "tech": "Tech",
    "ai": "Tech",
    "openai": "Tech",
    "science and technology": "Tech",
    
    # Entertainment
    "entertainment": "Entertainment",
    "movies": "Entertainment",
    "tv": "Entertainment",
    "music": "Entertainment",
    
    # Science
    "science": "Science",
    "climate": "Science",
    "space": "Science",
}

# Kalshi category → Sector mapping
KALSHI_CATEGORY_TO_SECTOR = {
    "World": "Politics",
    "Politics": "Politics",
    "US Politics": "Politics",
    "Climate and Weather": "Science",
    "Science and Technology": "Tech",
    "Economics": "Economics",
    "Financials": "Economics",
    "Entertainment": "Entertainment",
    "Sports": "Sports",
}


def get_sector_from_pm_tags(tags: list) -> str:
    """
    Determine sector from Polymarket tag objects.
    
    Args:
        tags: List of tag dicts with 'slug' and 'label' keys
    
    Returns:
        Normalized sector string
    """
    for tag in tags:
        slug = tag.get("slug", "").lower() if isinstance(tag, dict) else str(tag).lower()
        if slug in PM_TAG_TO_SECTOR:
            return PM_TAG_TO_SECTOR[slug]
    return "Other"


def get_sector_from_kalshi_category(category: str) -> str:
    """
    Map Kalshi event category to normalized sector.
    
    Args:
        category: Kalshi category string
    
    Returns:
        Normalized sector string
    """
    return KALSHI_CATEGORY_TO_SECTOR.get(category, "Other")


def extract_pm_tag_labels(tags: list) -> list[str]:
    """
    Extract tag labels from Polymarket tag objects.
    
    Args:
        tags: List of tag dicts with 'label' key
    
    Returns:
        List of tag label strings (max 10)
    """
    labels = []
    for tag in tags:
        if isinstance(tag, dict):
            label = tag.get("label", tag.get("slug", ""))
        else:
            label = str(tag)
        if label:
            labels.append(label)
    return labels[:10]
