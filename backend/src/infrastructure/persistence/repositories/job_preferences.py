"""
JobPreferences Repository Implementation
"""
from typing import List, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.persistence.models.preferences import JobPreferencesModel

class JobPreferencesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_unique_titles(self) -> List[str]:
        """Fetch all unique job titles from all users preferences"""
        result = await self.session.execute(
            select(JobPreferencesModel.job_titles)
        )
        all_lists = result.scalars().all()
        
        unique_titles: Set[str] = set()
        for title_list in all_lists:
            if title_list:
                for title in title_list:
                    if title:
                        unique_titles.add(title.strip().lower())
        
        return list(unique_titles)

    async def get_all_unique_locations(self) -> List[str]:
        """Fetch all unique locations from all users preferences"""
        result = await self.session.execute(
            select(JobPreferencesModel.locations)
        )
        all_lists = result.scalars().all()
        
        unique_locs: Set[str] = set()
        for loc_list in all_lists:
            if loc_list:
                for loc in loc_list:
                    if loc:
                        unique_locs.add(loc.strip())
        
        return list(unique_locs)

    async def get_all_preferences(self) -> List[JobPreferencesModel]:
        """Fetch all preferences for distribution logic"""
        result = await self.session.execute(select(JobPreferencesModel))
        return result.scalars().all()
