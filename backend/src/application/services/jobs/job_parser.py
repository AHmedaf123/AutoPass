"""
Job Parsing Utilities
Extract structured data from job descriptions
"""
import re
from typing import Optional, Tuple
from loguru import logger


def extract_job_id(url: str) -> Optional[str]:
    """
    Extract LinkedIn job ID from URL
    
    Examples:
    - https://www.linkedin.com/jobs/search/?currentJobId=4329656579&...
    - Returns: "4329656579"
    """
    if not url:
        return None
    
    # Pattern: currentJobId=(\d+)
    match = re.search(r'currentJobId=(\d+)', url)
    if match:
        return match.group(1)
    
    # Alternative: /jobs/view/(\d+)
    match = re.search(r'/jobs/view/(\d+)', url)
    if match:
        return match.group(1)
    
    return None


def parse_experience(description: str) -> Optional[int]:
    """
    Extract years of experience from job description
    
    Patterns matched:
    - "2+ years"
    - "3-5 years experience"
    - "minimum 2 years"
    - "1–3 years"
    
    Returns the minimum years mentioned
    """
    if not description:
        return None
    
    description_lower = description.lower()
    
    # Pattern: X+ years or X-Y years or X–Y years
    patterns = [
        r'(\d+)\+?\s*[-–]?\s*\d*\s*years?\s*(?:of\s+)?(?:experience|exp)?',
        r'(?:minimum|min|at\s+least)\s+(\d+)\s*\+?\s*years?',
        r'(\d+)\s*\+?\s*years?\s*(?:of\s+)?(?:professional|relevant|work)?',
        r'experience[:\s]+(\d+)\s*\+?\s*years?',
    ]
    
    years_found = []
    
    for pattern in patterns:
        matches = re.findall(pattern, description_lower)
        for match in matches:
            try:
                years = int(match)
                if 0 < years < 50:  # Sanity check
                    years_found.append(years)
            except (ValueError, TypeError):
                continue
    
    if years_found:
        return min(years_found)  # Return minimum required
    
    return None


def parse_salary(description: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """
    Extract salary range from job description
    
    Patterns matched:
    - "200K – 300K PKR"
    - "$50,000 - $80,000"
    - "150k-250k"
    - "50000 - 80000 USD"
    - "5 Lakh"
    
    Returns: (min_salary, max_salary, currency)
    """
    if not description:
        return None, None, None
    
    # Detect currency
    currency = "USD"  # Default
    if re.search(r'\bPKR\b', description, re.IGNORECASE):
        currency = "PKR"
    elif re.search(r'\brupees?\b', description, re.IGNORECASE):
        currency = "PKR"
    elif re.search(r'\$', description):
        currency = "USD"
    elif re.search(r'\bUSD\b', description, re.IGNORECASE):
        currency = "USD"
    elif re.search(r'\blakh\b', description, re.IGNORECASE):
        currency = "PKR"
    
    # Pattern for ranges like "200K-300K" or "200k – 300k"
    range_pattern = r'(\d+(?:,\d{3})*)\s*[kK]?\s*[-–to]+\s*(\d+(?:,\d{3})*)\s*[kK]?'
    match = re.search(range_pattern, description)
    
    if match:
        min_val = match.group(1).replace(',', '')
        max_val = match.group(2).replace(',', '')
        
        # Check if K suffix
        has_k = 'k' in match.group(0).lower()
        
        min_salary = int(min_val)
        max_salary = int(max_val)
        
        if has_k:
            min_salary *= 1000
            max_salary *= 1000
        
        return min_salary, max_salary, currency
    
    # Pattern for single values like "50K" or "100000"
    single_pattern = r'(?:salary|compensation|pay)[:\s]+(\d+(?:,\d{3})*)\s*[kK]?'
    match = re.search(single_pattern, description, re.IGNORECASE)
    
    if match:
        val = match.group(1).replace(',', '')
        salary = int(val)
        if 'k' in match.group(0).lower():
            salary *= 1000
        return salary, salary, currency
    
    # Pattern for Lakh (Indian/Pakistani)
    lakh_pattern = r'(\d+(?:\.\d+)?)\s*(?:lakh|lac)'
    match = re.search(lakh_pattern, description, re.IGNORECASE)
    
    if match:
        lakh_val = float(match.group(1))
        salary = int(lakh_val * 100000)
        return salary, salary, "PKR"
    
    return None, None, None


def parse_work_type(description: str) -> Optional[str]:
    """
    Extract work type from description
    
    Returns: "Remote", "Hybrid", "Onsite", or None
    """
    if not description:
        return None
    
    description_lower = description.lower()
    
    # Check for explicit mentions
    if re.search(r'\bremote\b', description_lower):
        if re.search(r'\bhybrid\b', description_lower):
            return "Hybrid"
        return "Remote"
    
    if re.search(r'\bhybrid\b', description_lower):
        return "Hybrid"
    
    if re.search(r'\bon[-\s]?site\b|\bonsite\b|\bin[-\s]?office\b', description_lower):
        return "Onsite"
    
    return None


def parse_location(description: str) -> Optional[str]:
    """
    Extract location from description if not already provided
    """
    if not description:
        return None
    
    # Common location patterns
    location_pattern = r'(?:location|based\s+in|office\s+in)[:\s]+([A-Za-z\s,]+?)(?:\n|$|\.)'
    match = re.search(location_pattern, description, re.IGNORECASE)
    
    if match:
        location = match.group(1).strip()
        if len(location) < 100:  # Sanity check
            return location
    
    return None
