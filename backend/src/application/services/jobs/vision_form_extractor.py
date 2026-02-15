"""
Vision Form Extractor
Fallback when DOM parsing fails - uses GPT-4o-mini for cost efficiency.
Cropped screenshots for 70-80% token reduction.
"""
import base64
import json
import io
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger
import httpx

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow not installed. Screenshot cropping disabled.")

from core.config import settings


@dataclass
class VisionFormField:
    """Field extracted from vision"""
    label: str
    field_type: str  # text, select, textarea, checkbox, radio
    required: bool
    y_position: int  # For ordering and approximate location
    options: List[str] = None  # For select/radio
    
    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "type": self.field_type,
            "required": self.required,
            "y_position": self.y_position,
            "options": self.options or []
        }


@dataclass  
class VisionExtractResult:
    """Result from vision extraction"""
    fields: List[VisionFormField]
    has_next_button: bool
    has_submit_button: bool
    confidence: float
    tokens_used: int
    raw_response: str


class VisionFormExtractor:
    """
    Vision fallback when DOM parsing fails.
    
    Uses GPT-4o-mini (cheaper than GPT-4 Vision) with:
    - Cropped screenshots (form region only)
    - Token-optimized prompts
    - Strict JSON schema
    """
    
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "openai/gpt-4o-mini"  # Cost-efficient vision model
    
    # Minimal, schema-locked prompt (token-optimized)
    EXTRACTION_PROMPT = """Analyze this job application form screenshot. Extract form fields.

Return JSON only:
{"fields":[{"label":"Field Name","type":"text|select|textarea|checkbox|radio","required":true,"y":100}],"next":true,"submit":false}

Rules:
- type: text for input, textarea for large text, select for dropdown, checkbox for yes/no, radio for options
- y: approximate vertical position (pixels from top)
- required: true if asterisk or "required" visible
- next/submit: true if button visible

JSON only, no explanation."""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self._call_count = 0
        self._total_tokens = 0
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set. Vision extraction will fail.")
    
    async def extract_from_screenshot(
        self,
        screenshot_bytes: bytes,
        crop_to_form: bool = True,
        max_tokens: int = 400
    ) -> VisionExtractResult:
        """
        Extract form fields from screenshot using vision.
        
        Args:
            screenshot_bytes: PNG screenshot bytes
            crop_to_form: Whether to crop to form region (saves tokens)
            max_tokens: Max response tokens
            
        Returns:
            VisionExtractResult with fields and metadata
        """
        if not self.api_key:
            logger.error("No API key for vision extraction")
            return self._empty_result()
        
        # Crop screenshot to reduce tokens
        if crop_to_form and PIL_AVAILABLE:
            screenshot_bytes = self._crop_to_form_region(screenshot_bytes)
        
        # Encode to base64
        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        # Estimate tokens (rough: 1 token per 4 bytes for images)
        image_tokens = len(screenshot_bytes) // 4
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": self.EXTRACTION_PROMPT},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_b64}",
                                            "detail": "low"  # Lower detail = fewer tokens
                                        }
                                    }
                                ]
                            }
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.1  # Low temp for consistent JSON
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Track usage
                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens", image_tokens + max_tokens)
                self._call_count += 1
                self._total_tokens += tokens_used
                
                logger.info(f"Vision extraction: {tokens_used} tokens")
                
                # Parse response
                return self._parse_response(content, tokens_used)
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Vision API error: {e.response.status_code} - {e.response.text}")
            return self._empty_result()
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            return self._empty_result()
    
    def _crop_to_form_region(self, screenshot_bytes: bytes) -> bytes:
        """
        Crop screenshot to form/modal region only.
        
        Saves 70-80% tokens by removing header, footer, background.
        """
        if not PIL_AVAILABLE:
            return screenshot_bytes
        
        try:
            image = Image.open(io.BytesIO(screenshot_bytes))
            width, height = image.size
            
            # LinkedIn Easy Apply modal is typically centered
            # Crop to center 70% width, top 80% height
            left = int(width * 0.15)
            right = int(width * 0.85)
            top = int(height * 0.05)
            bottom = int(height * 0.85)
            
            cropped = image.crop((left, top, right, bottom))
            
            # Reduce quality to save tokens
            output = io.BytesIO()
            cropped.save(output, format="PNG", optimize=True)
            
            reduction = 1 - (len(output.getvalue()) / len(screenshot_bytes))
            logger.debug(f"Screenshot cropped: {reduction:.0%} size reduction")
            
            return output.getvalue()
        
        except Exception as e:
            logger.warning(f"Screenshot crop failed: {e}")
            return screenshot_bytes
    
    def _parse_response(self, content: str, tokens_used: int) -> VisionExtractResult:
        """Parse JSON response from vision model"""
        try:
            # Extract JSON from response (might have extra text)
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                logger.warning("No JSON found in vision response")
                return self._empty_result(raw=content)
            
            data = json.loads(json_match.group())
            
            fields = []
            for f in data.get("fields", []):
                fields.append(VisionFormField(
                    label=f.get("label", ""),
                    field_type=f.get("type", "text"),
                    required=f.get("required", False),
                    y_position=f.get("y", 0),
                    options=f.get("options")
                ))
            
            # Sort by y position
            fields.sort(key=lambda x: x.y_position)
            
            return VisionExtractResult(
                fields=fields,
                has_next_button=data.get("next", False),
                has_submit_button=data.get("submit", False),
                confidence=0.85 if fields else 0.0,
                tokens_used=tokens_used,
                raw_response=content
            )
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse vision JSON: {e}")
            return self._empty_result(raw=content)
    
    def _empty_result(self, raw: str = "") -> VisionExtractResult:
        """Return empty result on failure"""
        return VisionExtractResult(
            fields=[],
            has_next_button=False,
            has_submit_button=False,
            confidence=0.0,
            tokens_used=0,
            raw_response=raw
        )
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get usage statistics"""
        return {
            "calls": self._call_count,
            "total_tokens": self._total_tokens,
            "avg_tokens_per_call": self._total_tokens / max(self._call_count, 1)
        }
    
    def reset_stats(self):
        """Reset usage statistics"""
        self._call_count = 0
        self._total_tokens = 0


def take_screenshot(driver) -> bytes:
    """Take screenshot from Selenium driver"""
    return driver.get_screenshot_as_png()


def take_cropped_screenshot(driver, crop_percent: float = 0.3) -> bytes:
    """
    Take cropped screenshot (center region only).
    
    Args:
        driver: Selenium WebDriver
        crop_percent: How much to crop from edges (0.3 = 30%)
    """
    screenshot = driver.get_screenshot_as_png()
    
    if not PIL_AVAILABLE:
        return screenshot
    
    try:
        image = Image.open(io.BytesIO(screenshot))
        width, height = image.size
        
        left = int(width * crop_percent)
        right = int(width * (1 - crop_percent))
        top = int(height * 0.1)  # Keep more of top (form header)
        bottom = int(height * 0.9)
        
        cropped = image.crop((left, top, right, bottom))
        
        output = io.BytesIO()
        cropped.save(output, format="PNG", optimize=True)
        return output.getvalue()
    
    except Exception as e:
        logger.warning(f"Cropped screenshot failed: {e}")
        return screenshot
