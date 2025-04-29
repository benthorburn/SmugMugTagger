import os
from pathlib import Path
import shutil
import json
from google.cloud import vision
import requests

class Setup:
    def __init__(self):
        self.app_dir = Path.home() / "Desktop" / "SmugMugTagger"
        self.credentials_dir = self.app_dir / "credentials"
        self.config_dir = self.app_dir / "config"
        
        # Create directories
        self.credentials_dir.mkdir(exist_ok=True)
        self.config_dir.mkdir(exist_ok=True)

    def setup_google_credentials(self):
        """Setup Google Cloud credentials"""
        print("\n1. Google Cloud Vision Setup")
        print("-------------------------")
        print("Please drag your Google Cloud credentials JSON file here")
        print("(or enter the full path to the file): ", end='')
        
        creds_path = input().strip().replace("'", "").replace('"', "")
        
        if not os.path.exists(creds_path):
            print(f"Error: File not found at {creds_path}")
            return False
            
        # Copy credentials
        dest_path = self.credentials_dir / "google_credentials.json"
        try:
            shutil.copy2(creds_path, dest_path)
            print("✓ Credentials file copied successfully")
        except shutil.SameFileError:
            print("✓ Using existing credentials file")
        
        # Create environment file
        with open(self.config_dir / ".env", "w") as f:
            f.write(f'GOOGLE_APPLICATION_CREDENTIALS="{str(dest_path)}"\n')
        
        return True

    def setup_smugmug(self):
        """Setup SmugMug credentials"""
        print("\n2. SmugMug Setup")
        print("---------------")
        print("Please enter your SmugMug API access token: ", end='')
        access_token = input().strip()
        print("Please enter your SmugMug API access token secret: ", end='')
        access_token_secret = input().strip()
        
        # Save SmugMug tokens
        tokens = {
            'access_token': access_token,
            'access_token_secret': access_token_secret
        }
        with open(self.config_dir / "smugmug_tokens.json", "w") as f:
            json.dump(tokens, f)
            
        return True

    def create_launcher(self):
        """Create the application launcher"""
        launcher_path = self.app_dir / "SmugMugTagger.command"
        with open(launcher_path, "w") as f:
            f.write(f'''#!/bin/bash
cd "{self.app_dir}"
source "{self.config_dir}/.env"
python3 tagger.py
''')
        os.chmod(launcher_path, 0o755)

    def setup(self):
        print("\nSmugMug Image Tagger Setup")
        print("=========================")
        
        if not self.setup_google_credentials():
            return False
            
        if not self.setup_smugmug():
            return False
            
        self.create_launcher()
        
        print("\n✓ Setup completed successfully!")
        print("\nYou can now:")
        print("1. Double-click SmugMugTagger.command on your desktop")
        print("2. Or run: python3 tagger.py from this directory")
        return True

if __name__ == "__main__":
    setup = Setup()
    setup.setup()