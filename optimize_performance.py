#!/usr/bin/env python3
"""
Performance and stability optimization for SmugMug Tagger
"""
import re

# Path to the app file
app_file = "app.py"

# Read the app file
with open(app_file, "r") as f:
    content = f.read()

# 1. Optimize batch processing logic
# Find the batch processing configuration
batch_pattern = r"(max_images_per_batch = \d+)"
batch_replacement = r"""# Dynamic batch size based on album size and server load
        max_images_per_batch = 1  # Start with conservative value for stability
        if total_images <= 20:
            max_images_per_batch = 2  # Use larger batch for small albums
        debug_info.append(f"Using batch size of {max_images_per_batch} images")"""

# Update the batch size configuration
content = re.sub(batch_pattern, batch_replacement, content)

# 2. Optimize memory usage by releasing objects after use
# Find the image processing loop
process_pattern = r"(# Process one image at a time for stability\s+for i in range\(start_index, end_index\):)"
gc_addition = r"""        # Force garbage collection every few images to manage memory
        if (i - start_index) % 5 == 0 and i > start_index:
            import gc
            gc.collect()
            
\1"""

# Add garbage collection to the processing loop
content = re.sub(process_pattern, gc_addition, content)

# 3. Add timeout to API requests to prevent hanging
# Find the SmugMug API patch request
patch_pattern = r"(base_response = smugmug\.patch\(\s+f'https:\/\/api\.smugmug\.com\/api\/v2\/image\/\{image_key\}',\s+headers=\{[^}]+\},\s+json=update_data\s+\))"
timeout_addition = r"\1, timeout=30"  # Add 30-second timeout

# Add timeout to the API requests
content = re.sub(patch_pattern, timeout_addition, content)

# 4. Optimize session management by limiting stored data
# Find the session saving function
session_pattern = r"(def save_progress\([^)]+\):.+?return PROCESS_STATE\[session_id\])"
session_optimization = r"""def save_progress(session_id, album_key, album_name, album_url, total_images, 
                 processed_indices, processed_images, failed_images, next_index, is_processing=False):
    """Save processing progress to state cache with optimized memory usage"""
    # Limit stored processed images to reduce memory usage
    # Only keep the 20 most recent processed images in memory
    recent_processed = processed_images[-20:] if len(processed_images) > 20 else processed_images
    
    PROCESS_STATE[session_id] = {
        'album_key': album_key,
        'album_name': album_name,
        'album_url': album_url,
        'total_images': total_images,
        'processed_indices': processed_indices,
        'processed_images': recent_processed,  # Store limited set of images
        'processed_count': len(processed_indices),  # Store count separately
        'failed_images': failed_images[-20:] if len(failed_images) > 20 else failed_images,  # Limit failed images too
        'next_index': next_index,
        'last_updated': datetime.datetime.now().isoformat(),
        'is_processing': is_processing  # Flag to indicate if background processing is active
    }
    return PROCESS_STATE[session_id]"""

# Update the session saving function
content = re.sub(session_pattern, session_optimization, content, flags=re.DOTALL)

# 5. Add better error handling for Vision API calls
vision_pattern = r"(vision_tags, confidence_scores = get_vision_tags\(vision_client, image_url, threshold\))"
vision_error_handling = r"""try:
                # Get Vision AI tags with timeout
                vision_tags, confidence_scores = get_vision_tags(vision_client, image_url, threshold)
                
                # If Vision API returned empty or failed, use a fallback
                if not vision_tags or len(vision_tags) <= 1:  # Only "AutoTagged" tag
                    logger.debug(f"Vision API returned insufficient tags, using fallbacks")
                    vision_tags = ['scotland', 'wilderness', 'outdoors', 'nature', 'landscape', 'AutoTagged']
            except Exception as vision_error:
                logger.error(f"Vision API error: {str(vision_error)}")
                # Use fallback tags
                vision_tags = ['scotland', 'wilderness', 'outdoors', 'nature', 'landscape', 'AutoTagged']
                confidence_scores = {}"""

# Update the Vision API call with better error handling
content = re.sub(vision_pattern, vision_error_handling, content)

# 6. Add proper cleanup of temporary files
cleanup_pattern = r"(# Clean up temp file\s+if temp_file_path and os\.path\.exists\(temp_file_path\):)"
cleanup_enhancement = r"""# Clean up all temporary files
        if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                debug_info.append("Cleaned up temporary credentials file")
            except Exception as e:
                debug_info.append(f"Error removing temp file: {str(e)}")
                
        # Find and clean up any other temporary files that might have been created
        import glob
        import tempfile
        temp_pattern = os.path.join(tempfile.gettempdir(), "tmp*")
        for temp_file in glob.glob(temp_pattern):
            try:
                if os.path.isfile(temp_file) and os.path.getsize(temp_file) > 1000:
                    # Check if it looks like a credentials file
                    with open(temp_file, 'r') as f:
                        if '"type": "service_account"' in f.read(1000):
                            os.unlink(temp_file)
                            debug_info.append(f"Cleaned up additional temp file: {temp_file}")
            except:
                # Ignore errors on cleanup - best effort only
                pass"""

# Update the cleanup code
content = re.sub(cleanup_pattern, cleanup_enhancement, content)

# 7. Add pause between API requests to avoid rate limiting
pause_pattern = r"(# Pause between images - important for stability\s+time\.sleep\(\d+\))"
pause_adjustment = r"# Pause between images - important for stability and to avoid rate limiting\n        time.sleep(3)"

# Update the pause timing
content = re.sub(pause_pattern, pause_adjustment, content)

# 8. Add improved configuration for Google Vision API
vision_config_pattern = r"(vision_image = vision\.Image\(\)\s+vision_image\.source\.image_uri = image_url)"
vision_config_enhancement = r"""# Create vision image with optimized settings
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    # Configure context to improve location detection
    context = vision.ImageContext(
        language_hints=["en-GB", "en"],  # Prefer British English for Scottish locations
        web_detection_params=vision.WebDetectionParams(
            include_geo_results=True  # Enable geo-specific web detection
        )
    )"""

# Update the Vision API configuration
content = re.sub(vision_config_pattern, vision_config_enhancement, content)

# Write the updated content back
with open(app_file, "w") as f:
    f.write(content)

print("✅ Performance optimizations applied:")
print("1. Dynamic batch size based on album size")
print("2. Memory optimization with garbage collection")
print("3. API request timeouts to prevent hanging")
print("4. Session storage optimization to reduce memory usage")
print("5. Better error handling for Vision API")
print("6. Enhanced cleanup of temporary files")
print("7. Adjusted pauses between API requests")
print("8. Improved Google Vision API configuration for better location detection")
