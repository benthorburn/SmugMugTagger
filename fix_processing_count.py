#!/usr/bin/env python3
"""
Fix for processing count discrepancy in the SmugMug Tagger app
"""
import json
import re

# Path to the templates file
templates_file = "templates/index.html"

# Read the template file
with open(templates_file, "r") as f:
    content = f.read()

# Find where progress calculations are happening
# Example 1: In the loadSessions function
sessions_progress_pattern = r"const progressPercent = \((?:session\.processed|data\.processed) \/ (?:session\.totalImages|data\.totalImages)\) \* 100;"
sessions_progress_replacement = r"const progressPercent = Math.min(Math.round((\1 / \2) * 100), 100);"

# Fix the sessions progress calculation
content = re.sub(sessions_progress_pattern, sessions_progress_replacement, content)

# Example 2: In the process response
process_progress_pattern = r"const progressPercent = totalImages > 0 \? (?:Math\.round\()?(?:\()?(processedCount \/ totalImages)(?: \* 100)(?:\))?(?:\))? : 0;"
process_progress_replacement = r"const progressPercent = totalImages > 0 ? Math.min(Math.round(\1 * 100), 100) : 0;"

# Fix the process progress calculation
content = re.sub(process_progress_pattern, process_progress_replacement, content)

# Add validation for processed count in the backend (app.py)
app_file = "app.py"
with open(app_file, "r") as f:
    app_content = f.read()

# Find where the progress is calculated for the response
response_pattern = r"(processed_images\.extend\(new_processed\);.+?failedCount\": len\(failed_images\),)"
response_validation = r"\1\n            # Ensure processed count doesn't exceed total images\n            processed_count = min(len(processed_indices), total_images),"

# Add validation for the processed count
app_content = re.sub(response_pattern, response_validation, app_content)

# Also modify processed_indices counting logic to avoid duplicates
indices_pattern = r"(processed_indices\.extend\(updated_indices\))"
indices_validation = r"# Ensure no duplicate indices\nprocessed_indices = list(set(processed_indices + updated_indices))"

app_content = re.sub(indices_pattern, indices_validation, app_content)

# Write the updated content back
with open(templates_file, "w") as f:
    f.write(content)

with open(app_file, "w") as f:
    f.write(app_content)

print("✅ Fixed processing count calculations in frontend and backend")
print("The UI should now display accurate progress percentages capped at 100%")
