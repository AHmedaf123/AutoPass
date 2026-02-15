"""
Test PDF generation for extracted resume
"""
import sys
import json
import asyncio
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent / "backend" / "src"))

from application.services.resume.temp_resume_generator import TempResumeGeneratorService


async def test_pdf_generation():
    """Test PDF generation from extracted resume JSON"""
    
    # Load the extracted resume
    resume_file = Path(__file__).parent / "output" / "resume_80ab4bc5-0d49-48e2-8786-a8f2e07056cb.json"
    
    if not resume_file.exists():
        print(f"❌ Resume file not found: {resume_file}")
        return
    
    with open(resume_file, 'r', encoding='utf-8') as f:
        resume_json = json.load(f)
    
    print("✅ Loaded resume JSON")
    print(f"\nBasic Info Structure:")
    basic_info = resume_json.get("basic_info", {})
    print(f"  - Has 'name': {basic_info.get('name')}")
    print(f"  - Has 'content': {'content' in basic_info}")
    print(f"  - Has 'contact': {'contact' in basic_info}")
    
    if "contact" in basic_info:
        contact = basic_info["contact"]
        print(f"\nContact Info:")
        print(f"  - Email: {contact.get('email')}")
        print(f"  - Phone: {contact.get('phone')}")
        print(f"  - LinkedIn: {contact.get('linkedin')}")
        print(f"  - GitHub: {contact.get('github')}")
        print(f"  - Location: {contact.get('location')}")
    
    # Generate PDF
    print("\n🔧 Generating PDF...")
    generator = TempResumeGeneratorService()
    
    try:
        pdf_bytes = await generator.generate_temp_resume(resume_json)
        
        # Save PDF
        output_file = Path(__file__).parent / "output" / "test_resume_80ab4bc5.pdf"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'wb') as f:
            f.write(pdf_bytes)
        
        print(f"✅ PDF generated successfully!")
        print(f"📄 Saved to: {output_file}")
        print(f"📊 Size: {len(pdf_bytes):,} bytes")
        
    except Exception as e:
        print(f"❌ Error generating PDF: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_pdf_generation())
