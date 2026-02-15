"""
Clean Preferences API Endpoints
Simplified preferences management matching requirements
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Form, Query
from datetime import datetime
from loguru import logger
from dataclasses import replace

from presentation.api.v1.schemas.preferences_clean import (
    PreferencesCreateRequest,
    PreferencesResponse,
    PreferencesUpdateRequest
)
from domain.entities import User
from presentation.api.v1.dependencies import get_current_user
from presentation.api.v1.container import get_user_repository
from application.repositories.interfaces import IUserRepository


router = APIRouter()


def _map_experience_to_years(level: str) -> dict:
    """Map experience level to years dict"""
    mapping = {
        'Internship': {'exp_years_internship': 0},
        'Entry Level': {'exp_years_entry_level': 1},
        'Associate': {'exp_years_associate': 3},
        'Mid-Senior': {'exp_years_mid_senior_level': 5},
        'Director': {'exp_years_director': 8},
        'Executive': {'exp_years_executive': 10}
    }
    return mapping.get(level, {'exp_years_entry_level': 1})


def _map_work_type(work_type: str) -> dict:
    """Map work type to boolean preferences"""
    return {
        'pref_remote': work_type == 'Remote',
        'pref_hybrid': work_type == 'Hybrid',
        'pref_onsite': work_type == 'Onsite'
    }


@router.post("/preferences", response_model=PreferencesResponse, status_code=status.HTTP_201_CREATED)
async def create_preferences(
    user_id: str = Form(..., description="User ID (UID)"),
    job_titles: str = Form(..., description="Comma-separated job titles"),
    location_city: str = Form(..., description="City name"),
    location_country: str = Form(..., description="Country name"),
    work_type: str = Form(..., description="Remote, Hybrid, or Onsite"),
    experience_level: str = Form(..., description="Internship, Entry Level, Associate, Mid-Senior, Director, or Executive"),
    current_salary: Optional[int] = Form(None, description="Current salary in USD"),
    desired_salary: Optional[int] = Form(None, description="Desired salary in USD"),
    gender: Optional[str] = Form(None, description="Gender: Male, Female, Other"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """
    Create user preferences.
    
    **Required Parameters:**
    - user_id: User ID (UID) from login response
    - job_titles: Comma-separated (e.g., "Software Engineer, Python Developer")
    - location_city: City name
    - location_country: Country name
    - work_type: Remote, Hybrid, or Onsite (only one)
    - experience_level: Internship, Entry Level, Associate, Mid-Senior, Director, or Executive (only one)
    
    **Optional Parameters:**
    - current_salary: Current salary in USD (used for form filling)
    - desired_salary: Desired salary in USD (used for form filling)
    - gender: Gender (Male, Female, Other)
    """
    try:
        # Validate UID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )
        
        # Get user
        current_user = await user_repo.get_by_id(user_uuid)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate request data
        request_data = PreferencesCreateRequest(
            job_titles=job_titles,
            location_city=location_city,
            location_country=location_country,
            work_type=work_type,
            experience_level=experience_level,
            current_salary=current_salary,
            desired_salary=desired_salary,
            gender=gender
        )
        
        # Parse job titles
        titles_list = [t.strip() for t in request_data.job_titles.split(',')]
        
        # Get current user state
        user = await user_repo.get_by_id(current_user.id)
        
        # Prepare updates
        exp_updates = _map_experience_to_years(request_data.experience_level)
        work_type_updates = _map_work_type(request_data.work_type)
        
        location_full = f"{request_data.location_city}, {request_data.location_country}"
        
        # Update user entity
        updated_user = replace(
            user,
            # Job titles
            job_title_priority_1=titles_list[0] if len(titles_list) > 0 else None,
            job_title_priority_2=titles_list[1] if len(titles_list) > 1 else None,
            job_title_priority_3=titles_list[2] if len(titles_list) > 2 else None,
            target_job_title=titles_list[0] if len(titles_list) > 0 else "",
            
            # Location (stored in industry field as per current schema)
            industry=location_full,
            
            # Work type preferences
            **work_type_updates,
            
            # Experience years
            **exp_updates,
            
            # Salary preferences
            current_salary=current_salary,
            desired_salary=desired_salary,
            
            # Gender
            gender=gender,
            
            updated_at=datetime.utcnow()
        )
        
        await user_repo.update(updated_user)
        
        logger.info(f"Created preferences for user {current_user.id}")
        
        return PreferencesResponse(
            user_id=str(updated_user.id),
            job_titles=titles_list,
            location_city=request_data.location_city,
            location_country=request_data.location_country,
            work_type=request_data.work_type,
            experience_level=request_data.experience_level,
            current_salary=request_data.current_salary,
            desired_salary=request_data.desired_salary,
            gender=request_data.gender,
            resume_uploaded=True,
            created_at=updated_user.created_at.isoformat() if updated_user.created_at else None,
            updated_at=updated_user.updated_at.isoformat() if updated_user.updated_at else None
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create preferences: {str(e)}"
        )


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    user_id: str = Query(..., description="User ID (UID)"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """
    Get user preferences.
    
    **Parameters:**
    - user_id: User ID (UID) from login response (as query parameter)
    """
    try:
        # Validate UID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )
        
        # Get user
        user = await user_repo.get_by_id(user_uuid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        # Build response fields from stored user preferences
        titles = [t for t in [user.job_title_priority_1, user.job_title_priority_2, user.job_title_priority_3] if t]

        # industry holds "City, Country" per current schema
        city, country = "", ""
        if user.industry:
            parts = [p.strip() for p in user.industry.split(",")]
            if parts:
                city = parts[0]
            if len(parts) > 1:
                country = parts[1]

        if user.pref_remote:
            work_type = "Remote"
        elif user.pref_hybrid:
            work_type = "Hybrid"
        elif user.pref_onsite:
            work_type = "Onsite"
        else:
            work_type = "Remote"

        exp_level = "Entry Level"
        if user.exp_years_internship is not None:
            exp_level = "Internship"
        elif user.exp_years_mid_senior_level is not None:
            exp_level = "Mid-Senior"
        elif user.exp_years_associate is not None:
            exp_level = "Associate"
        elif user.exp_years_director is not None:
            exp_level = "Director"
        elif user.exp_years_executive is not None:
            exp_level = "Executive"

        return PreferencesResponse(
            user_id=str(user.id),
            job_titles=titles,
            location_city=city,
            location_country=country,
            work_type=work_type,
            experience_level=exp_level,
            current_salary=getattr(user, 'current_salary', None),
            desired_salary=getattr(user, 'desired_salary', None),
            gender=getattr(user, 'gender', None),
            resume_uploaded=bool(user.resume_url or user.resume_base64),
            created_at=user.created_at.isoformat() if user.created_at else None,
            updated_at=user.updated_at.isoformat() if user.updated_at else None
        )
    
    except Exception as e:
        logger.error(f"Error getting preferences for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get preferences: {str(e)}"
        )


@router.patch("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    user_id: str = Form(..., description="User ID (UID)"),
    job_titles: Optional[str] = Form(None, description="Comma-separated job titles"),
    location_city: Optional[str] = Form(None, description="City name"),
    location_country: Optional[str] = Form(None, description="Country name"),
    work_type: Optional[str] = Form(None, description="Remote, Hybrid, or Onsite"),
    experience_level: Optional[str] = Form(None, description="Experience level"),
    current_salary: Optional[int] = Form(None, description="Current salary in USD"),
    desired_salary: Optional[int] = Form(None, description="Desired salary in USD"),
    gender: Optional[str] = Form(None, description="Gender: Male, Female, Other"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """
    Update user preferences (all fields optional).
    
    **Parameters:**
    - user_id: User ID (UID) from login response
    - All other fields are optional
    """
    try:
        # Validate UID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )
        
        # Get user
        current_user = await user_repo.get_by_id(user_uuid)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Create update request
        request = PreferencesUpdateRequest(
            job_titles=job_titles,
            location_city=location_city,
            location_country=location_country,
            work_type=work_type,
            experience_level=experience_level,
            current_salary=current_salary,
            desired_salary=desired_salary,
            gender=gender
        )
        
        # Update user fields
        update_kwargs = {}
        
        if request.job_titles:
            titles = [t.strip() for t in request.job_titles.split(',')]
            update_kwargs['job_title_priority_1'] = titles[0] if len(titles) > 0 else None
            update_kwargs['job_title_priority_2'] = titles[1] if len(titles) > 1 else None
            update_kwargs['job_title_priority_3'] = titles[2] if len(titles) > 2 else None
        
        if request.location_city or request.location_country:
            location = f"{request.location_city}, {request.location_country}".strip(', ')
            update_kwargs['industry'] = location
        
        if request.work_type:
            work_type_update = _map_work_type(request.work_type)
            update_kwargs.update(work_type_update)
        
        if request.experience_level:
            exp_update = _map_experience_to_years(request.experience_level)
            update_kwargs.update(exp_update)
        
        # Add salary fields to update if provided
        if current_salary is not None:
            update_kwargs['current_salary'] = current_salary
        if desired_salary is not None:
            update_kwargs['desired_salary'] = desired_salary
        if gender is not None:
            update_kwargs['gender'] = gender
        
        # Create updated user entity (frozen dataclass requires replace())
        updated_user_entity = replace(current_user, **update_kwargs)
        
        # Update user via repository
        updated_user = await user_repo.update(updated_user_entity)
        
        return PreferencesResponse(
            user_id=str(updated_user.id),
            job_titles=[
                updated_user.job_title_priority_1,
                updated_user.job_title_priority_2,
                updated_user.job_title_priority_3
            ],
            location_city=request.location_city or '',
            location_country=request.location_country or '',
            work_type=request.work_type or 'Remote',
            experience_level=request.experience_level or 'Entry Level',
            current_salary=getattr(updated_user, 'current_salary', None),
            desired_salary=getattr(updated_user, 'desired_salary', None),
            gender=getattr(updated_user, 'gender', None),
            resume_uploaded=bool(updated_user.resume_url or updated_user.resume_base64),
            created_at=updated_user.created_at.isoformat() if updated_user.created_at else None,
            updated_at=updated_user.updated_at.isoformat() if updated_user.updated_at else None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating preferences for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preferences: {str(e)}"
        )

