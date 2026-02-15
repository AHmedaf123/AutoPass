"""
Script to extract user resume JSON from database
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

# Add backend/src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "src"))

from core.database import get_db_session
from infrastructure.persistence.repositories.user import SQLAlchemyUserRepository


async def extract_user_resume(uid: str):
    """Extract and print user's resume JSON"""
    try:
        user_uuid = UUID(uid)
    except ValueError:
        print(f"❌ Invalid UID format: {uid}")
        return
    
    async with get_db_session() as session:
        user_repo = SQLAlchemyUserRepository(session)
        user = await user_repo.get_by_id(user_uuid)
        
        if not user:
            print(f"❌ User not found: {uid}")
            return
        
        print(f"\n✅ Found User: {user.full_name} ({user.email})")
        print(f"   Phone: {getattr(user, 'phone', 'N/A')}")
        print(f"   Has Resume: {'Yes' if user.resume_parsed_data else 'No'}")
        
        if user.resume_parsed_data:
            # Parse resume data
            if isinstance(user.resume_parsed_data, str):
                resume_data = json.loads(user.resume_parsed_data)
            else:
                resume_data = user.resume_parsed_data
            
            print(f"\n📄 Resume Structure:")
            print(f"   Keys: {list(resume_data.keys())}")
            
            # Check basic_info
            basic_info = resume_data.get("basic_info", {})
            print(f"\n📇 Basic Info Structure:")
            print(f"   Type: {type(basic_info)}")
            if isinstance(basic_info, dict):
                print(f"   Keys: {list(basic_info.keys())}")
                if "content" in basic_info:
                    print(f"   Content Keys: {list(basic_info['content'].keys()) if isinstance(basic_info['content'], dict) else 'Not a dict'}")
                    content = basic_info['content']
                    print(f"\n   📧 Contact Details in basic_info.content:")
                    print(f"      Name: {content.get('name') or content.get('full_name') or 'N/A'}")
                    print(f"      Email: {content.get('email') or 'N/A'}")
                    print(f"      Phone: {content.get('phone') or content.get('phone_number') or 'N/A'}")
                    print(f"      LinkedIn: {content.get('linkedin') or content.get('linkedin_url') or 'N/A'}")
                    print(f"      GitHub: {content.get('github') or content.get('github_url') or 'N/A'}")
                    print(f"      Location: {content.get('location') or content.get('city') or 'N/A'}")
                else:
                    print(f"\n   📧 Contact Details in basic_info (flat):")
                    print(f"      Name: {basic_info.get('name') or basic_info.get('full_name') or 'N/A'}")
                    print(f"      Email: {basic_info.get('email') or 'N/A'}")
                    print(f"      Phone: {basic_info.get('phone') or basic_info.get('phone_number') or 'N/A'}")
                    print(f"      LinkedIn: {basic_info.get('linkedin') or basic_info.get('linkedin_url') or 'N/A'}")
                    print(f"      GitHub: {basic_info.get('github') or basic_info.get('github_url') or 'N/A'}")
            
            # Check contact at root level
            contact = resume_data.get("contact", {})
            if contact:
                print(f"\n📞 Contact at Root Level:")
                print(f"   {contact}")
            
            # Save to file
            output_file = Path(__file__).parent / "output" / f"resume_{uid}.json"
            output_file.parent.mkdir(exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(resume_data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Full resume saved to: {output_file}")
            
            # Print full JSON pretty
            print(f"\n📋 Full Resume JSON:")
            print("=" * 80)
            print(json.dumps(resume_data, indent=2, ensure_ascii=False))
            print("=" * 80)
        else:
            print(f"\n⚠️ No resume data found for this user")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_user_resume.py <UID>")
        sys.exit(1)
    
    uid = sys.argv[1]
    asyncio.run(extract_user_resume(uid))
