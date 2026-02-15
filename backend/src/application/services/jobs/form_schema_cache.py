"""
Form Schema Cache
Cache form schemas by page hash - avoid re-extraction.
Button location cache per domain.
"""
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger
import hashlib


@dataclass
class CachedSchema:
    """Cached form schema with metadata"""
    page_hash: str
    fields: List[Any]  # List of FormField
    has_next: bool
    has_submit: bool
    source: str  # "dom" or "vision"
    created_at: datetime = field(default_factory=datetime.utcnow)
    hit_count: int = 0
    
    def is_expired(self, max_age_hours: int = 24) -> bool:
        """Check if cache entry is expired"""
        age = datetime.utcnow() - self.created_at
        return age > timedelta(hours=max_age_hours)


@dataclass
class ButtonLocations:
    """Cached button selectors for a domain"""
    next_selectors: List[str]
    submit_selectors: List[str]
    last_success: Dict[str, str] = field(default_factory=dict)  # action -> selector that worked


class FormSchemaCache:
    """
    Cache form schemas by page hash - avoid re-extraction.
    
    Benefits:
    - Same form structure = same hash = cache hit
    - Saves vision API calls on multi-application sessions
    - Button selectors cached per domain
    """
    
    DEFAULT_NEXT_SELECTORS = [
        "//button[contains(@aria-label, 'Continue')]",
        "//button[contains(@aria-label, 'Next')]",
        "//button[contains(., 'Next')]",
        "//button[contains(., 'Continue')]",
        "//button[contains(., 'Review')]",
        "//span[text()='Next']/ancestor::button",
    ]
    
    DEFAULT_SUBMIT_SELECTORS = [
        "//button[contains(@aria-label, 'Submit application')]",
        "//button[contains(@aria-label, 'Submit')]",
        "//button[contains(., 'Submit application')]",
        "//button[contains(., 'Submit')]",
        "//button[contains(., 'Apply')]",
        "//span[text()='Submit application']/ancestor::button",
    ]
    
    def __init__(self, max_cache_size: int = 100):
        """
        Initialize cache.
        
        Args:
            max_cache_size: Max number of schemas to cache
        """
        self._schema_cache: Dict[str, CachedSchema] = {}
        self._button_cache: Dict[str, ButtonLocations] = {}
        self._max_size = max_cache_size
        
        # Stats
        self._hits = 0
        self._misses = 0
    
    def get_schema(self, page_hash: str) -> Optional[CachedSchema]:
        """
        Get cached schema by page hash.
        
        Returns None if not found or expired.
        """
        cached = self._schema_cache.get(page_hash)
        
        if cached:
            if cached.is_expired():
                del self._schema_cache[page_hash]
                self._misses += 1
                return None
            
            cached.hit_count += 1
            self._hits += 1
            logger.debug(f"Cache HIT for hash {page_hash[:8]}... (hits: {cached.hit_count})")
            return cached
        
        self._misses += 1
        return None
    
    def cache_schema(
        self,
        page_hash: str,
        fields: List[Any],
        has_next: bool,
        has_submit: bool,
        source: str = "dom"
    ) -> None:
        """
        Cache a form schema.
        
        Args:
            page_hash: Hash of page structure
            fields: List of form fields
            has_next: Whether page has next button
            has_submit: Whether page has submit button
            source: Where fields came from ("dom" or "vision")
        """
        # Evict oldest if at capacity
        if len(self._schema_cache) >= self._max_size:
            self._evict_oldest()
        
        self._schema_cache[page_hash] = CachedSchema(
            page_hash=page_hash,
            fields=fields,
            has_next=has_next,
            has_submit=has_submit,
            source=source
        )
        
        logger.debug(f"Cached schema {page_hash[:8]}... ({len(fields)} fields, source={source})")
    
    def _evict_oldest(self) -> None:
        """Evict oldest cache entry"""
        if not self._schema_cache:
            return
        
        oldest_hash = min(
            self._schema_cache.keys(),
            key=lambda h: self._schema_cache[h].created_at
        )
        del self._schema_cache[oldest_hash]
    
    def get_button_locations(self, domain: str = "linkedin.com") -> ButtonLocations:
        """
        Get cached button selectors for domain.
        
        Returns default selectors if not cached.
        """
        if domain not in self._button_cache:
            self._button_cache[domain] = ButtonLocations(
                next_selectors=self.DEFAULT_NEXT_SELECTORS.copy(),
                submit_selectors=self.DEFAULT_SUBMIT_SELECTORS.copy()
            )
        
        return self._button_cache[domain]
    
    def update_button_success(self, domain: str, action: str, selector: str) -> None:
        """
        Record which selector worked for a button.
        
        Future lookups will try this selector first.
        """
        buttons = self.get_button_locations(domain)
        buttons.last_success[action] = selector
        
        # Move successful selector to front of list
        if action == "next" and selector in buttons.next_selectors:
            buttons.next_selectors.remove(selector)
            buttons.next_selectors.insert(0, selector)
        elif action == "submit" and selector in buttons.submit_selectors:
            buttons.submit_selectors.remove(selector)
            buttons.submit_selectors.insert(0, selector)
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        return {
            "size": len(self._schema_cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(total, 1),
            "domains_cached": len(self._button_cache)
        }
    
    def clear(self) -> None:
        """Clear all caches"""
        self._schema_cache.clear()
        self._button_cache.clear()
        self._hits = 0
        self._misses = 0


# Global cache instance (singleton pattern)
_global_cache: Optional[FormSchemaCache] = None


def get_form_cache() -> FormSchemaCache:
    """Get global form schema cache"""
    global _global_cache
    if _global_cache is None:
        _global_cache = FormSchemaCache()
    return _global_cache
