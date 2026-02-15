"""
Domain Enums
Business enumerations for the application
"""
from enum import Enum
from typing import Dict, List


class Industry(str, Enum):
    """Supported industries for job search (exactly 16)"""
    CONSULTING = "Consulting"
    CREATIVE_DESIGN = "Creative & Design"
    CUSTOMER_SERVICE = "Customer Service"
    DATA_ANALYTICS = "Data & Analytics"
    EDUCATION = "Education"
    ENGINEERING = "Engineering"
    FINANCE_ACCOUNTING = "Finance & Accounting"
    HEALTHCARE = "Healthcare"
    HUMAN_RESOURCE = "Human Resource"
    LEGAL = "Legal"
    MARKETING_SALES = "Marketing & Sales"
    OPERATIONS = "Operations"
    PRODUCT = "Product"
    SALES_BUSINESS = "Sales & Business"
    SCIENCE_RESEARCH = "Science & Research"
    TECHNOLOGY_IT = "Technology & IT"


# Industry-specific subfields mapping (BLS-standardized occupational titles, 2025-aligned)
# Exact mapping per BLS Occupational Outlook Handbook
INDUSTRY_SUBFIELDS: Dict[Industry, List[str]] = {
    Industry.CONSULTING: [
        "Management Analysts",
        "Market Research Analysts",
        "Financial Analysts",
        "Budget Analysts",
        "Operations Research Analysts",
        "Logisticians"
    ],
    Industry.CREATIVE_DESIGN: [
        "Graphic Designers",
        "Art Directors",
        "Industrial Designers",
        "Fashion Designers",
        "Interior Designers",
        "Multimedia Artists and Animators",
        "Craft and Fine Artists"
    ],
    Industry.CUSTOMER_SERVICE: [
        "Customer Service Representatives",
        "Receptionists",
        "Information Clerks",
        "General Office Clerks",
        "Secretaries and Administrative Assistants",
        "Telecommunicators",
        "Financial Clerks"
    ],
    Industry.DATA_ANALYTICS: [
        "Mathematicians and Statisticians",
        "Operations Research Analysts",
        "Actuaries",
        "Survey Researchers",
        "Logisticians",
        "Data Scientists"  # BLS Math group update
    ],
    Industry.EDUCATION: [
        "Postsecondary Teachers",
        "Kindergarten and Elementary School Teachers",
        "Middle School Teachers",
        "Special Education Teachers",
        "Career and Technical Education Teachers",
        "Instructional Coordinators",
        "Adult Literacy and GED Teachers"
    ],
    Industry.ENGINEERING: [
        "Aerospace Engineers",
        "Biomedical Engineers",
        "Civil Engineers",
        "Electrical and Electronics Engineers",
        "Environmental Engineers",
        "Industrial Engineers",
        "Mechanical Engineers"
    ],
    Industry.FINANCE_ACCOUNTING: [
        "Accountants and Auditors",
        "Financial Analysts",
        "Personal Financial Advisors",
        "Loan Officers",
        "Budget Analysts",
        "Financial Examiners",
        "Tax Examiners and Collectors"
    ],
    Industry.HEALTHCARE: [
        "Registered Nurses",
        "Physicians and Surgeons",
        "Physician Assistants",
        "Physical Therapists",
        "Occupational Therapists",
        "Speech-Language Pathologists",
        "Diagnostic Medical Sonographers"
    ],
    Industry.HUMAN_RESOURCE: [
        "Human Resources Specialists",
        "Training and Development Managers",
        "Compensation and Benefits Managers",
        "Management Analysts",
        "Logisticians",
        "Financial Managers",
        "Administrative Services Managers"
    ],
    Industry.LEGAL: [
        "Lawyers",
        "Paralegals and Legal Assistants",
        "Court Reporters and Simultaneous Captioners",
        "Arbitrators, Mediators, and Conciliators",
        "Judges and Hearing Officers",
        "Legal Support Workers"
    ],
    Industry.MARKETING_SALES: [
        "Advertising Sales Agents",
        "Insurance Sales Agents",
        "Securities, Commodities, and Financial Services Sales Agents",
        "Real Estate Brokers and Sales Agents",
        "Wholesale and Manufacturing Sales Representatives",
        "Sales Engineers"
    ],
    Industry.OPERATIONS: [
        "Industrial Production Managers",
        "Administrative Services and Facilities Managers",
        "Logisticians",
        "Operations Research Analysts",
        "Construction Managers",
        "Food Service Managers",
        "Purchasing Managers and Buyers"
    ],
    Industry.PRODUCT: [
        "Computer and Information Systems Managers",
        "Industrial Production Managers",
        "Marketing Managers",
        "Industrial Designers",
        "Graphic Designers",
        "Art Directors"
    ],
    Industry.SALES_BUSINESS: [
        "Retail Sales Workers",
        "Cashiers",
        "Advertising Sales Agents",
        "Insurance Sales Agents",
        "Wholesale and Manufacturing Sales Representatives",
        "Real Estate Brokers and Sales Agents",
        "Securities, Commodities, and Financial Services Sales Agents"
    ],
    Industry.SCIENCE_RESEARCH: [
        "Medical Scientists",
        "Biochemists and Biophysicists",
        "Microbiologists",
        "Chemists and Materials Scientists",
        "Environmental Scientists and Specialists",
        "Geoscientists",
        "Epidemiologists"
    ],
    Industry.TECHNOLOGY_IT: [
        "Software Developers, Quality Assurance Analysts, and Testers",
        "Computer and Information Research Scientists",
        "Computer Systems Analysts",
        "Database Administrators and Architects",
        "Network and Computer Systems Administrators",
        "Computer Support Specialists",
        "Computer Programmers"
    ]
}


def get_subfields_for_industry(industry: Industry) -> List[str]:
    """Get available subfields for a given industry"""
    return INDUSTRY_SUBFIELDS.get(industry, [])


def validate_subfield(industry: Industry, subfield: str) -> bool:
    """Validate if a subfield belongs to an industry"""
    return subfield in INDUSTRY_SUBFIELDS.get(industry, [])


class WorkType(str, Enum):
    """Work type preferences for jobs"""
    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ONSITE = "Onsite"


class ApplicationStatus(str, Enum):
    """Status of job application"""
    PENDING = "Pending"
    APPLIED = "Applied"
    EXPIRED = "Expired"
    INTERVIEWING = "Interviewing"
    REJECTED = "Rejected"
    ACCEPTED = "Accepted"


class WorkModel(str, Enum):
    """Detailed work models for user preferences"""
    ONSITE = "Onsite"
    HYBRID = "Hybrid"
    OPEN_TO_REMOTE = "Open to Remote"
    FULLY_REMOTE = "Fully Remote"


class JobType(str, Enum):
    """Job type classifications"""
    INTERNSHIP = "Internship"
    CONTRACT = "Contract"
    FULL_TIME = "Full Time"
    PART_TIME = "Part Time"
    TEMPORARY = "Temporary"


class ExperienceLevel(str, Enum):
    """Experience level classifications"""
    INTERNSHIP = "Internship"
    ENTRY_LEVEL = "Entry Level"
    ASSOCIATE = "Associate"
    MID_SENIOR_LEVEL = "Mid-Senior Level"
    DIRECTOR = "Director"
    EXECUTIVE = "Executive"
