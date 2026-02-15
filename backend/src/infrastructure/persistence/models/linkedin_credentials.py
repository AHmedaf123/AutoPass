"""
LinkedIn Credentials ORM Model
Encrypted storage of LinkedIn credentials
"""
import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class LinkedInCredentialsModel(Base):
    """LinkedIn credentials table (encrypted)"""
    
    __tablename__ = "linkedin_credentials"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign Key
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Encrypted Credentials
    email_encrypted = Column(String(500), nullable=False)
    password_encrypted = Column(String(500), nullable=False)
    
    def __repr__(self):
        return f"<LinkedInCredentialsModel user_id={self.user_id}>"
