"""
Preferences API Schemas
Dynamic schema for flexible user preferences
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class PreferencesUpdateRequest(BaseModel):
    """
    Request model for updating explicit user preferences (Unified Table)
    """
    # Job Titles (Ranked)
    job_title_priority_1: Optional[str] = None
    job_title_priority_2: Optional[str] = None
    job_title_priority_3: Optional[str] = None
    
    # Experience (Years by level)
    exp_years_internship: Optional[int] = None
    exp_years_entry_level: Optional[int] = None
    exp_years_associate: Optional[int] = None
    exp_years_mid_senior_level: Optional[int] = None
    exp_years_director: Optional[int] = None
    exp_years_executive: Optional[int] = None
    
    # Work Type Preferences
    pref_onsite: Optional[bool] = False
    pref_hybrid: Optional[bool] = False
    pref_remote: Optional[bool] = False

class PreferencesResponse(BaseModel):
    """Response model for explicit user preferences"""
    user_id: str
    
    job_title_priority_1: Optional[str] = None
    job_title_priority_2: Optional[str] = None
    job_title_priority_3: Optional[str] = None
    
    exp_years_internship: Optional[int] = None
    exp_years_entry_level: Optional[int] = None
    exp_years_associate: Optional[int] = None
    exp_years_mid_senior_level: Optional[int] = None
    exp_years_director: Optional[int] = None
    exp_years_executive: Optional[int] = None
    
    pref_onsite: bool = False
    pref_hybrid: bool = False
    pref_remote: bool = False
    
    updated_at: Optional[str] = None
