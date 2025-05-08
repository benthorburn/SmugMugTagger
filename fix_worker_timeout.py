#!/usr/bin/env python3
"""
Fix for worker timeout issues in SmugMug Tagger app
"""
import re

def modify_gunicorn_config():
    """Create or modify a Gunicorn configuration file to increase timeouts"""
    try:
        # Check if Procfile exists
        with open("Procfile", "r") as f:
            procfile_content = f.read()
        
        # Check if it's a simple Procfile without timeout settings
        if "timeout" not in procfile_content:
            # Create a modified Procfile with increased timeout
            with open("Procfile", "w") as f:
                f.write("web: gunicorn app:app --timeout 120 --workers 2 --threads 2\n")
            print("✅ Updated Procfile with increased timeout (120s)")
        else:
            print("ℹ️ Procfile already has custom gunicorn settings")
        
        return True
    except FileNotFoundError:
        # Create new Procfile
        with open("Procfile", "w") as f:
            f.write("web: gunicorn app:app --timeout 120 --workers 2 --threads 2\n")
        print("✅ Created new Procfile with increased timeout (120s)")
        return True
    except Exception as e:
        print(f"❌ Error modifying Gunicorn config: {str(e)}")
        return False

def optimize_image_processing():
    """Optimize image processing to prevent timeouts"""
    try:
        # Path to the app file
        app_file = "app.py"
        
        # Read the app file
        with open(app_file, "r") as f:
            content = f.read()
        
        # 1. Reduce batch size for processing to minimize timeouts
        batch_size_pattern = r"max_images_per_batch = (\d+)"
        if re.search(batch_size_pattern, content):
            content = re.sub(
                batch_size_pattern,
                "max_images_per_batch = 1  # Reduced to prevent timeouts",
                content
            )
            print("✅ Reduced batch size to 1 to prevent timeouts")
        
        # 2. Add timeout to API requests
        if "timeout=" not in content:
            api_request_pattern = r"(smugmug\.get\([^)]+\))"
            if re.search(api_request_pattern, content):
                content = re.sub(
                    api_request_pattern,
                    r"\1, timeout=30",
                    content
                )
                print("✅ Added timeouts to API requests")
        
        # 3. Skip large images that might cause timeouts
        if "# Skip large images" not in content:
            # Find the image processing loop
            process_pattern = r"for i in range\(start_index, end_index\):"
            image_check = """
            # Skip large images that might cause timeouts
            try:
                image_size = 0
                if 'ArchivedSize' in image:
                    image_size = int(image['ArchivedSize'])
                elif 'OriginalSize' in image:
                    image_size = int(image['OriginalSize'])
                
                # Skip images larger than 10MB
                if image_size > 10 * 1024 * 1024:
                    logger.warning(f"Skipping large image {image.get('FileName', 'Unknown')} ({image_size/1024/1024:.1f}MB)")
                    failed_images.append(f"{image.get('FileName', 'Unknown')} (too large)")
                    continue
            except Exception as size_error:
                # Continue even if we can't determine size
                logger.debug(f"Could not determine image size: {str(size_error)}")
            
"""
            # Insert image size check after the loop starts
            if re.search(process_pattern, content):
                match = re.search(process_pattern, content)
                insert_pos = match.end()
                indentation = re.match(r"(\s*)", content[match.start():]).group(1)
                
                # Adjust indentation to match the pattern
                indented_check = "\n".join(indentation + "    " + line for line in image_check.strip().split("\n"))
                
                content = content[:insert_pos] + indented_check + content[insert_pos:]
                print("✅ Added large image detection and skipping")
        
        # 4. Add garbage collection after processing each image
        if "gc.collect()" not in content:
            # Find where to insert garbage collection
            process_end_pattern = r"processed_indices\.add\(i\)"
            if re.search(process_end_pattern, content):
                gc_code = """
            # Force garbage collection after each image to manage memory
            if i % 2 == 0:  # Run GC every 2 images
                import gc
                gc.collect()
"""
                # Insert after we've processed an image
                match = re.search(process_end_pattern, content)
                insert_pos = match.end()
                indentation = re.match(r"(\s*)", content[match.start():]).group(1)
                
                # Adjust indentation to match the pattern
                indented_gc = "\n".join(indentation + line for line in gc_code.strip().split("\n"))
                
                content = content[:insert_pos] + "\n" + indented_gc + content[insert_pos:]
                print("✅ Added garbage collection to manage memory")
        
        # Write the updated content back
        with open(app_file, "w") as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"❌ Error optimizing image processing: {str(e)}")
        return False

def add_error_recovery():
    """Add enhanced error recovery to continue processing after errors"""
    try:
        # Path to the app file
        app_file = "app.py"
        
        # Read the app file
        with open(app_file, "r") as f:
            content = f.read()
        
        # Check if error recovery is already added
        if "# Recovery mechanism for interrupted processing" in content:
            print("✓ Error recovery already implemented")
            return True
        
        # Add recovery mechanism to background processing
        background_pattern = r"def process_album_background\(session_id, start_index, batch_size=\d+\):"
        if re.search(background_pattern, content):
            recovery_code = """
    # Recovery mechanism for interrupted processing
    def resume_interrupted_processing():
        """Resume any interrupted processing sessions"""
        try:
            for session_id, state in PROCESS_STATE.items():
                # Check if this session was marked as processing but is no longer active
                if state.get('is_processing', False) and session_id not in BACKGROUND_TASKS:
                    next_index = state.get('next_index', -1)
                    
                    # If processing was incomplete, restart it
                    if next_index != -1:
                        logger.info(f"Resuming interrupted processing for session {session_id} from index {next_index}")
                        
                        # Start a new background thread
                        background_thread = threading.Thread(
                            target=process_album_background,
                            args=(session_id, next_index, 1)  # Use batch size of 1 for stability
                        )
                        background_thread.daemon = True
                        background_thread.start()
                        
                        # Store thread reference
                        BACKGROUND_TASKS[session_id] = background_thread
        except Exception as e:
            logger.error(f"Error in resume_interrupted_processing: {str(e)}")
            logger.error(traceback.format_exc())
    
    # Try to resume any interrupted processing on startup
    threading.Timer(30, resume_interrupted_processing).start()
"""
            # Find a good place to insert the recovery code
            status_route = "@app.route('/status')"
            
            if status_route in content:
                insert_pos = content.find(status_route)
                content = content[:insert_pos] + recovery_code + "\n" + content[insert_pos:]
                print("✅ Added processing recovery mechanism")
            else:
                print("⚠️ Could not find a place to insert recovery code")
        else:
            print("⚠️ Could not find background processing function")
        
        # Write the updated content back
        with open(app_file, "w") as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"❌ Error adding error recovery: {str(e)}")
        return False

def add_requirements():
    """Add any missing requirements"""
    try:
        # Read current requirements
        with open("requirements.txt", "r") as f:
            requirements = f.read()
        
        # Check for missing requirements and add them
        missing_requirements = []
        
        if "psutil" not in requirements:
            missing_requirements.append("psutil==5.9.5")
        
        if "Pillow" not in requirements:
            missing_requirements.append("Pillow==9.5.0")
        
        # Add missing requirements
        if missing_requirements:
            with open("requirements.txt", "a") as f:
                f.write("\n# Added for performance monitoring and optimization\n")
                for req in missing_requirements:
                    f.write(f"{req}\n")
            
            print(f"✅ Added {len(missing_requirements)} missing requirements")
        else:
            print("✓ All necessary requirements already present")
        
        return True
    except Exception as e:
        print(f"❌ Error updating requirements: {str(e)}")
        return False

if __name__ == "__main__":
    print("Applying fixes for worker timeout issues...")
    
    # Apply fixes
    gunicorn_configured = modify_gunicorn_config()
    processing_optimized = optimize_image_processing()
    recovery_added = add_error_recovery()
    requirements_updated = add_requirements()
    
    if all([gunicorn_configured, processing_optimized, recovery_added, requirements_updated]):
        print("\n✅ All fixes applied successfully!")
        print("\nTo use these fixes:")
        print("1. Push the changes to GitHub")
        print("2. Deploy to Render")
        print("3. The app should now handle larger images better and recover from interruptions")
    else:
        print("\n⚠️ Some fixes could not be applied. Check the errors above.")
