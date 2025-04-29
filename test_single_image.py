from google.cloud import vision
from requests_oauthlib import OAuth1Session
import json
import os
from pathlib import Path

def test_smugmug_connection():
    """Test SmugMug connection and get a single image"""
    print("\nTesting SmugMug connection...")
    
    # Load credentials
    config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
    with open(config_file) as f:
        tokens = json.load(f)
    
    # Create SmugMug session
    api_key = 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq'
    api_secret = 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR'
    
    smugmug = OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=tokens['access_token'],
        resource_owner_secret=tokens['access_token_secret']
    )
    
    # Get user info
    response = smugmug.get(
        'https://api.smugmug.com/api/v2!authuser',
        headers={'Accept': 'application/json'}
    )
    
    if response.status_code == 200:
        user_data = response.json()
        nickname = user_data['Response']['User']['NickName']
        print(f"Connected as user: {nickname}")
        
        # Get recent images using the correct endpoint
        print("\nFetching recent images...")
        images_url = f'https://api.smugmug.com/api/v2/user/{nickname}!recentimages'
        
        response = smugmug.get(
            images_url,
            params={
                'count': 1,
                'Extras': 'FileName,WebUrl,Keywords,Uri,ImageKey,Title,DateUploaded'
            },
            headers={'Accept': 'application/json'}
        )
        
        print(f"Images response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if 'Response' in data and 'Image' in data['Response']:
                images = data['Response']['Image']
                if images:
                    print(f"Found {len(images)} recent images")
                    return smugmug, images[0]
                else:
                    print("No images found in response")
            else:
                print("Unexpected response structure:", json.dumps(data, indent=2))
        else:
            print(f"Error fetching images: {response.text}")
    
    return None, None

def test_vision_api(image_url):
    """Test Google Vision API with a single image"""
    print("\nTesting Google Vision API...")
    
    # Set up credentials
    creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
    
    # Create vision client
    vision_client = vision.ImageAnnotatorClient()
    
    # Create image object
    image = vision.Image()
    image.source.image_uri = image_url
    
    # Detect labels
    response = vision_client.label_detection(image=image)
    labels = response.label_annotations
    
    print("\nDetected labels:")
    for label in labels:
        print(f"- {label.description} ({label.score:.2%} confidence)")
    
    return [label.description.lower() for label in labels]

def update_image_keywords(smugmug, image, new_keywords):
    """Update image with new keywords"""
    print("\nUpdating image keywords...")
    
    # Get existing keywords
    existing_keywords = set(image.get('Keywords', '').split(',')) if image.get('Keywords') else set()
    existing_keywords.discard('')
    
    print(f"Existing keywords: {', '.join(existing_keywords) if existing_keywords else 'None'}")
    print(f"New keywords: {', '.join(new_keywords)}")
    
    # Combine with new keywords
    all_keywords = existing_keywords.union(new_keywords)
    
    # Update image
    response = smugmug.patch(
        image['Uri'],
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
        json={'Keywords': ','.join(all_keywords)}
    )
    
    print(f"Update response status: {response.status_code}")
    
    if response.status_code == 200:
        print("✓ Successfully updated image keywords")
        print(f"Added {len(new_keywords)} new tags")
    else:
        print(f"✗ Failed to update keywords: {response.status_code}")
        print(f"Response: {response.text}")

def main():
    print("SmugMug Single Image Test")
    print("========================")
    
    # Test SmugMug connection and get an image
    smugmug, image = test_smugmug_connection()
    
    if not image:
        print("No image found or error connecting to SmugMug")
        return
    
    # Test Vision API on the image
    print(f"\nProcessing image: {image['FileName']}")
    print(f"Image URL: {image['WebUrl']}")
    
    new_tags = test_vision_api(image['WebUrl'])
    
    if new_tags:
        # Update image with new tags
        update_image_keywords(smugmug, image, new_tags)
    else:
        print("No tags generated for image")

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")