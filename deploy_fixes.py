#!/usr/bin/env python3
"""
Commit and push fixes to GitHub for deployment
"""
import subprocess
import datetime
import os

def commit_and_push():
    """Commit changes and push to GitHub"""
    try:
        # Get the current branch
        result = subprocess.run(['git', 'branch', '--show-current'], 
                                capture_output=True, text=True)
        current_branch = result.stdout.strip()
        
        print(f"Current branch: {current_branch}")
        
        # Create a new branch for the fixes
        branch_name = f"fixes-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
        
        # Check if git is initialized
        if not os.path.exists('.git'):
            print("Initializing git repository...")
            subprocess.run(['git', 'init'])
        
        # Create and checkout the new branch
        subprocess.run(['git', 'checkout', '-b', branch_name])
        print(f"Created new branch: {branch_name}")
        
        # Add all changes
        subprocess.run(['git', 'add', '.'])
        print("Added all changes")
        
        # Commit changes
        commit_message = "Fix processing count discrepancy and worker timeout issues"
        subprocess.run(['git', 'commit', '-m', commit_message])
        print(f"Committed changes with message: '{commit_message}'")
        
        # Get the remote URL
        result = subprocess.run(['git', 'remote', '-v'], 
                                capture_output=True, text=True)
        remote_info = result.stdout.strip()
        
        if not remote_info:
            # Prompt for remote URL
            print("\nNo git remote found. Please enter your GitHub repository URL:")
            remote_url = input("> ")
            
            if remote_url:
                subprocess.run(['git', 'remote', 'add', 'origin', remote_url])
                print(f"Added remote: origin -> {remote_url}")
        
        # Push to GitHub
        print("\nDo you want to push these changes to GitHub now? (y/n)")
        push_now = input("> ").lower() == 'y'
        
        if push_now:
            subprocess.run(['git', 'push', '-u', 'origin', branch_name])
            print(f"Pushed changes to GitHub branch: {branch_name}")
        
        print("\n✅ Changes ready for deployment!")
        print("\nTo deploy these fixes to Render:")
        
        if not push_now:
            print("1. Push to GitHub with:")
            print(f"   git push -u origin {branch_name}")
            print("2. Create a pull request on GitHub")
        else:
            print("1. Create a pull request on GitHub")
        
        print("2. After merging, Render will automatically deploy the updated application")
        print("3. If you prefer to manually deploy:")
        print("   - Log in to Render.com")
        print("   - Go to your SmugMugTagger service")
        print("   - Click 'Manual Deploy' > 'Deploy latest commit'")
        
        return True
    except Exception as e:
        print(f"❌ Error during git operations: {str(e)}")
        return False

if __name__ == "__main__":
    print("Preparing to deploy fixes...")
    commit_and_push()
