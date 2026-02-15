#!/usr/bin/env python
"""Fix corrupted numeric section in single_job_applier.py"""

file_path = r'e:\JOB\Auto-Applier\AutoPASS\backend\src\application\services\jobs\single_job_applier.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix line 1192 (index 1191) which has the corruption
line_idx = 1191
if line_idx < len(lines):
    old_line = lines[line_idx]
    print(f"Old line {line_idx+1}: {repr(old_line[:150])}")
    
    # Replace escaped \n with actual newlines and \" with "
    fixed_line = old_line.replace('\\n', '\n').replace('\\"', '"')
    lines[line_idx] = fixed_line
    
    print(f"Fixed line {line_idx+1}")
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("✓ File updated successfully")
else:
    print(f"✗ Line index {line_idx} out of range")
