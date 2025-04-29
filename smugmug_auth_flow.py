from rauth import OAuth1Service
import webbrowser
import json
from pathlib import Path
import time

class SmugMugAuth:
    def __init__(self):
        self.api_key = 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq'
        self.api_secret = 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR'
        
        # SmugMug OAuth endpoints
        self.request_token_url = 'https://secure.smugmug.com/services/oauth/1.0a/getRequestToken'
        self.access_token_url = 'https://secure.smugmug.com/services/oauth/1.0a/getAccessToken'
        self.authorize_url = 'https://secure.smugmug.com/services/oauth/1.0a/authorize'
        
        # Create OAuth1Service
        self.service = OAuth1Service(
            name='smugmug-image-tagger',
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            request_token_url=self.request_token_url,
            access_token_url=self.access_token_url,
            authorize_url=self.authorize_url,
            base_url='https://api.smugmug.com/api/v2'
        )

    def get_auth_tokens(self):
        """Complete OAuth flow and get access tokens"""
        # Step 1: Get request token
        request_token, request_token_secret = self.service.get_request_token(
            params={'oauth_callback': 'oob'}
        )
        
        # Step 2: Get authorize URL and open in browser
        auth_url = self.service.get_authorize_url(
            request_token,
            params={'Access': 'Full', 'Permissions': 'Modify'}
        )
        
        print("\nOpening browser for authorization...")
        webbrowser.open(auth_url)
        
        # Step 3: Get verification code from user
        print("\nPlease authorize the application in your browser.")
        print("After authorizing, you'll see a verification code.")
        verifier = input("Enter the verification code here: ").strip()
        
        # Step 4: Get access token
        session = self.service.get_auth_session(
            request_token,
            request_token_secret,
            method='GET',
            data={'oauth_verifier': verifier}
        )
        
        # Extract access tokens
        access_token = session.access_token
        access_token_secret = session.access_token_secret
        
        # Save tokens
        tokens = {
            'access_token': access_token,
            'access_token_secret': access_token_secret
        }
        
        config_dir = Path.home() / "Desktop" / "SmugMugTagger" / "config"
        config_dir.mkdir(exist_ok=True)
        
        with open(config_dir / "smugmug_tokens.json", "w") as f:
            json.dump(tokens, f)
            
        print("\n✓ Access tokens saved successfully!")
        
        # Test the connection
        test_response = session.get(
            'https://api.smugmug.com/api/v2!authuser',
            headers={'Accept': 'application/json'}
        )
        
        if test_response.status_code == 200:
            user_data = test_response.json()
            print(f"\nSuccessfully connected as: {user_data['Response']['User']['NickName']}")
            return True
        else:
            print(f"\nError testing connection: {test_response.status_code}")
            return False

def main():
    print("SmugMug Authentication Setup")
    print("===========================")
    
    auth = SmugMugAuth()
    success = auth.get_auth_tokens()
    
    if success:
        print("\nAuthentication completed successfully!")
    else:
        print("\nAuthentication failed. Please try again.")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()