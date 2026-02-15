"""
LinkedIn URL Builder
Dynamically generates LinkedIn job search URLs from user preferences
"""
from typing import Optional, List
from urllib.parse import quote
from loguru import logger


class LinkedInURLBuilder:
    """
    Build LinkedIn job search URLs dynamically from user preferences.
    Ensures all filters are embedded in URL parameters.
    """
    
    # LinkedIn location to geoId mapping
    LOCATION_TO_GEOID = {
        "lahore": "104112529",
        "lahore, pakistan": "104112529",
        "karachi": "104112529",
        "karachi, pakistan": "104112529",
        "islamabad": "104112529",
        "islamabad, pakistan": "104112529",
        "pakistan": "104112529",
        "united states": "103663517",
        "us": "103663517",
        "usa": "103663517",
        "canada": "102713980",
        "united kingdom": "101165590",
        "uk": "101165590",
        "india": "102713980",
        "remote": "104112529",  # Default to Pakistan for remote
    }
    
    # Experience level to LinkedIn filter code mapping
    EXPERIENCE_LEVEL_MAP = {
        "internship": "1",
        "entry level": "2",
        "entry": "2",
        "associate": "3",
        "mid-senior level": "4",
        "mid-senior": "4",
        "mid": "4",
        "senior": "4",
        "director": "5",
        "executive": "6"
    }
    
    # Work type to LinkedIn filter code mapping
    WORK_TYPE_MAP = {
        "on-site": "1",
        "onsite": "1",
        "on site": "1",
        "remote": "2",
        "hybrid": "3"
    }
    
    @staticmethod
    def build_job_search_url(
        keywords: str,
        location: str,
        experience_level: Optional[str] = None,
        work_type: Optional[str] = None,
        easy_apply: bool = True,
        current_job_id: Optional[str] = None,
        start: int = 0
    ) -> str:
        """
        Build a LinkedIn job search URL with all filters embedded.
        
        Args:
            keywords: Job title or keywords to search
            location: Location name (e.g., "Pakistan", "Remote", "United States")
            experience_level: Experience level (e.g., "Entry level", "Mid-Senior level")
            work_type: Work type preference (e.g., "Remote", "Hybrid", "Onsite")
            easy_apply: Include Easy Apply filter
            current_job_id: Optional job ID for direct job view
            start: Pagination start index (for multi-page results)
            
        Returns:
            Complete LinkedIn job search URL with all filters
            
        Example:
            >>> builder = LinkedInURLBuilder()
            >>> url = builder.build_job_search_url(
            ...     keywords="Software Engineer",
            ...     location="Pakistan",
            ...     experience_level="Mid-Senior level",
            ...     work_type="Remote",
            ...     easy_apply=True
            ... )
            >>> print(url)
            https://www.linkedin.com/jobs/search/?f_AL=true&f_E=4&f_WT=2&geoId=104112529&keywords=Software%20Engineer&origin=JOB_SEARCH_PAGE_SEARCH_BUTTON&refresh=true
        """
        # Base URL
        url = "https://www.linkedin.com/jobs/search/?"
        
        # Parameter list (to be joined at the end)
        params = []
        
        # 1. Add currentJobId first if provided
        if current_job_id:
            params.append(f"currentJobId={current_job_id}")
        
        # 2. Add Easy Apply filter
        if easy_apply:
            params.append("f_AL=true")
        
        # 3. Add experience level filter (f_E parameter)
        if experience_level:
            exp_code = LinkedInURLBuilder.EXPERIENCE_LEVEL_MAP.get(experience_level.lower())
            if exp_code:
                params.append(f"f_E={exp_code}")
                logger.debug(f"Added experience level filter: {experience_level} (f_E={exp_code})")
            else:
                logger.warning(f"Unknown experience level: {experience_level}")
        
        # 4. Add work type filter (f_WT parameter)
        if work_type:
            wt_code = LinkedInURLBuilder.WORK_TYPE_MAP.get(work_type.lower())
            if wt_code:
                params.append(f"f_WT={wt_code}")
                logger.debug(f"Added work type filter: {work_type} (f_WT={wt_code})")
            else:
                logger.warning(f"Unknown work type: {work_type}")
        
        # 5. Add geoId for location
        geo_id = LinkedInURLBuilder.LOCATION_TO_GEOID.get(
            location.lower(), 
            "104112529"  # Default to Pakistan
        )
        params.append(f"geoId={geo_id}")
        logger.debug(f"Location '{location}' mapped to geoId={geo_id}")
        
        # 6. Add keywords (URL-encoded)
        keywords_encoded = quote(keywords)
        params.append(f"keywords={keywords_encoded}")
        
        # 7. Add origin
        params.append("origin=JOB_SEARCH_PAGE_SEARCH_BUTTON")
        
        # 8. Add refresh
        params.append("refresh=true")
        
        # 9. Add pagination if needed
        if start > 0:
            params.append(f"start={start}")
        
        # Join all parameters
        url += "&".join(params)
        
        logger.info(f"Generated LinkedIn URL: {url}")
        return url
    
    @staticmethod
    def build_multiple_urls(
        job_titles: List[str],
        location: str,
        experience_level: Optional[str] = None,
        work_type: Optional[str] = None,
        easy_apply: bool = True
    ) -> List[dict]:
        """
        Build multiple LinkedIn job search URLs for multiple job titles.
        
        Args:
            job_titles: List of job titles to search
            location: Location name
            experience_level: Experience level filter
            work_type: Work type filter
            easy_apply: Include Easy Apply filter
            
        Returns:
            List of dictionaries with job_title and url keys
            
        Example:
            >>> builder = LinkedInURLBuilder()
            >>> urls = builder.build_multiple_urls(
            ...     job_titles=["Software Engineer", "Data Scientist"],
            ...     location="Pakistan",
            ...     experience_level="Mid-Senior level",
            ...     work_type="Remote"
            ... )
            >>> for item in urls:
            ...     print(f"{item['job_title']}: {item['url']}")
        """
        urls = []
        for job_title in job_titles:
            url = LinkedInURLBuilder.build_job_search_url(
                keywords=job_title,
                location=location,
                experience_level=experience_level,
                work_type=work_type,
                easy_apply=easy_apply
            )
            urls.append({
                "job_title": job_title,
                "url": url
            })
        
        logger.info(f"Generated {len(urls)} LinkedIn search URLs")
        return urls
    
    @staticmethod
    def validate_location(location: str) -> bool:
        """Check if location is valid/mapped"""
        return location.lower() in LinkedInURLBuilder.LOCATION_TO_GEOID
    
    @staticmethod
    def validate_experience_level(experience_level: str) -> bool:
        """Check if experience level is valid/mapped"""
        return experience_level.lower() in LinkedInURLBuilder.EXPERIENCE_LEVEL_MAP
    
    @staticmethod
    def validate_work_type(work_type: str) -> bool:
        """Check if work type is valid/mapped"""
        return work_type.lower() in LinkedInURLBuilder.WORK_TYPE_MAP
