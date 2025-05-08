#!/usr/bin/env python3
"""
Targeted fix for processing count discrepancy in SmugMug Tagger app
This is a more direct approach than the previous script
"""
import json

def fix_index_html():
    """Fix the progress calculation in the frontend"""
    try:
        # Path to the templates file
        templates_file = "templates/index.html"
        
        # Read the template file
        with open(templates_file, "r") as f:
            content = f.read()
        
        # Fix 1: Make sure progress percentage is capped at 100%
        content = content.replace(
            "const progressPercent = (session.processed / session.totalImages) * 100;",
            "const progressPercent = Math.min(Math.round((session.processed / session.totalImages) * 100), 100);"
        )
        
        # Fix 2: Cap the progress percentage in the process response
        content = content.replace(
            "const progressPercent = totalImages > 0 ? Math.round((processedCount / totalImages) * 100) : 0;",
            "const progressPercent = totalImages > 0 ? Math.min(Math.round((processedCount / totalImages) * 100), 100) : 0;"
        )
        
        # Fix 3: Ensure the displayed processed count never exceeds total images
        content = content.replace(
            "${processedCount} of ${totalImages}",
            "${Math.min(processedCount, totalImages)} of ${totalImages}"
        )
        
        # Write the fixed content back
        with open(templates_file, "w") as f:
            f.write(content)
        
        print("✅ Fixed progress calculation in index.html")
        return True
    except Exception as e:
        print(f"❌ Error fixing index.html: {str(e)}")
        return False

def fix_app_py():
    """Fix the backend tracking of processed counts"""
    try:
        # Path to the app file
        app_file = "app.py"
        
        # Read the app file
        with open(app_file, "r") as f:
            content = f.read()
        
        # Fix 1: Make processed_indices a set to automatically remove duplicates
        content = content.replace(
            "processed_indices = []",
            "processed_indices = set()"
        )
        
        # Fix 2: Update how indices are added (use set.add instead of list.append)
        content = content.replace(
            "processed_indices.append(i)",
            "processed_indices.add(i)"
        )
        
        # Fix 3: Update how indices are extended
        content = content.replace(
            "processed_indices.extend(updated_indices)",
            "processed_indices.update(updated_indices)"
        )
        
        # Fix 4: Ensure processed_indices is converted to list for JSON serialization
        content = content.replace(
            "'processed_indices': processed_indices,",
            "'processed_indices': list(processed_indices),"
        )
        
        # Fix 5: Add a reset mechanism for the PROCESS_STATE
        if "def reset_session(session_id):" not in content:
            reset_function = """
def reset_session(session_id):
    """Reset the processing state for a session"""
    if session_id in PROCESS_STATE:
        state = PROCESS_STATE[session_id]
        # Reset counters but keep album info
        PROCESS_STATE[session_id] = {
            'album_key': state.get('album_key', ''),
            'album_name': state.get('album_name', 'Unknown Album'),
            'album_url': state.get('album_url', ''),
            'total_images': state.get('total_images', 0),
            'processed_indices': [],
            'processed_images': [],
            'failed_images': [],
            'next_index': 0,
            'last_updated': datetime.datetime.now().isoformat(),
            'is_processing': False
        }
        return True
    return False
"""
            # Find a good place to insert the function
            insert_pos = content.find("def get_session(session_id):")
            if insert_pos > 0:
                content = content[:insert_pos] + reset_function + "\n" + content[insert_pos:]
        
        # Write the fixed content back
        with open(app_file, "w") as f:
            f.write(content)
        
        print("✅ Fixed processing count tracking in app.py")
        return True
    except Exception as e:
        print(f"❌ Error fixing app.py: {str(e)}")
        return False

def add_reset_endpoint():
    """Add an endpoint to manually reset a session"""
    try:
        # Path to the app file
        app_file = "app.py"
        
        # Read the app file
        with open(app_file, "r") as f:
            content = f.read()
        
        # Check if endpoint already exists
        if "@app.route('/reset-session/<session_id>', methods=['POST'])" in content:
            print("✓ Reset endpoint already exists")
            return True
        
        # Create the endpoint
        reset_endpoint = """
@app.route('/reset-session/<session_id>', methods=['POST'])
def reset_session_endpoint(session_id):
    """Reset a specific session"""
    if reset_session(session_id):
        return jsonify({"success": True, "message": "Session reset"})
    
    return jsonify({"error": "Session not found"}), 404
"""
        
        # Find a good place to insert the endpoint
        insert_pos = content.find("@app.route('/clear-session/")
        if insert_pos > 0:
            content = content[:insert_pos] + reset_endpoint + "\n" + content[insert_pos:]
        else:
            # Alternative insertion point
            insert_pos = content.find("@app.route('/status')")
            if insert_pos > 0:
                content = content[:insert_pos] + reset_endpoint + "\n" + content[insert_pos:]
        
        # Write the updated content back
        with open(app_file, "w") as f:
            f.write(content)
        
        print("✅ Added reset session endpoint")
        return True
    except Exception as e:
        print(f"❌ Error adding reset endpoint: {str(e)}")
        return False

def add_reset_button():
    """Add a reset button to the UI"""
    try:
        # Path to the templates file
        templates_file = "templates/index.html"
        
        # Read the template file
        with open(templates_file, "r") as f:
            content = f.read()
        
        # Check if button already exists
        if "resetSession" in content:
            print("✓ Reset button already exists")
            return True
        
        # Add the reset function
        reset_function = """
        function resetSession(sessionId) {
            if (!confirm('Are you sure you want to reset this session? This will clear all progress information but maintain the session.')) {
                return;
            }
            
            fetch(`/reset-session/${sessionId}`, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        alert(data.error);
                    } else {
                        loadSessions();
                        alert('Session reset successfully.');
                    }
                })
                .catch(error => {
                    alert(`Error resetting session: ${error.message}`);
                });
        }
"""
        
        # Find a good place to insert the function
        insert_pos = content.find("function clearSession(")
        if insert_pos > 0:
            content = content[:insert_pos] + reset_function + content[insert_pos:]
        
        # Add the button to the session actions
        content = content.replace(
            '<button class="btn-sm btn-danger" onclick="clearSession(\'${session.id}\')">Clear</button>',
            '<button class="btn-sm btn-secondary" onclick="resetSession(\'${session.id}\')">Reset</button>\n                                        <button class="btn-sm btn-danger" onclick="clearSession(\'${session.id}\')">Clear</button>'
        )
        
        # Write the updated content back
        with open(templates_file, "w") as f:
            f.write(content)
        
        print("✅ Added reset button to UI")
        return True
    except Exception as e:
        print(f"❌ Error adding reset button: {str(e)}")
        return False

def cleanup_process_state():
    """Add code to periodically clean up PROCESS_STATE to prevent memory issues"""
    try:
        # Path to the app file
        app_file = "app.py"
        
        # Read the app file
        with open(app_file, "r") as f:
            content = f.read()
        
        # Check if cleanup function already exists
        if "def cleanup_old_sessions():" in content:
            print("✓ Cleanup function already exists")
            return True
        
        # Create the cleanup function
        cleanup_function = """
def cleanup_old_sessions(max_age_hours=48):
    """Clean up old sessions from PROCESS_STATE"""
    current_time = datetime.datetime.now()
    sessions_to_remove = []
    
    for session_id, state in PROCESS_STATE.items():
        # Skip if no last_updated timestamp
        if 'last_updated' not in state:
            continue
            
        try:
            # Parse last_updated timestamp
            last_updated = datetime.datetime.fromisoformat(state['last_updated'])
            
            # Calculate age in hours
            age_hours = (current_time - last_updated).total_seconds() / 3600
            
            # Add to removal list if older than max_age_hours
            if age_hours > max_age_hours:
                sessions_to_remove.append(session_id)
        except (ValueError, TypeError):
            # If we can't parse the timestamp, skip this session
            continue
    
    # Remove old sessions
    for session_id in sessions_to_remove:
        del PROCESS_STATE[session_id]
    
    return len(sessions_to_remove)
"""
        
        # Find a good place to insert the function
        insert_pos = content.find("def save_progress(")
        if insert_pos > 0:
            content = content[:insert_pos] + cleanup_function + "\n" + content[insert_pos:]
        
        # Add a call to the cleanup function in the sessions endpoint
        sessions_endpoint = "@app.route('/sessions', methods=['GET'])"
        if sessions_endpoint in content:
            sessions_pos = content.find(sessions_endpoint)
            sessions_func_start = content.find("def list_sessions():", sessions_pos)
            
            if sessions_func_start > 0:
                sessions_func_body_start = content.find("    sessions = []", sessions_func_start)
                
                if sessions_func_body_start > 0:
                    cleanup_call = "    # Clean up old sessions\n    cleanup_old_sessions()\n\n"
                    content = content[:sessions_func_body_start] + cleanup_call + content[sessions_func_body_start:]
        
        # Write the updated content back
        with open(app_file, "w") as f:
            f.write(content)
        
        print("✅ Added session cleanup mechanism")
        return True
    except Exception as e:
        print(f"❌ Error adding cleanup mechanism: {str(e)}")
        return False

if __name__ == "__main__":
    print("Applying targeted fixes for processing count discrepancy...")
    
    # Apply fixes
    frontend_fixed = fix_index_html()
    backend_fixed = fix_app_py()
    reset_endpoint_added = add_reset_endpoint()
    reset_button_added = add_reset_button()
    cleanup_added = cleanup_process_state()
    
    if all([frontend_fixed, backend_fixed, reset_endpoint_added, reset_button_added, cleanup_added]):
        print("\n✅ All fixes applied successfully!")
        print("\nTo use these fixes:")
        print("1. Push the changes to GitHub")
        print("2. Deploy to Render")
        print("3. After deployment, use the new 'Reset' button on any problematic sessions")
        print("4. Start processing new albums or reset existing ones")
    else:
        print("\n⚠️ Some fixes could not be applied. Check the errors above.")
