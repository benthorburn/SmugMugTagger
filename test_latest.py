from requests_oauthlib import OAuth1Session
from google.cloud import vision
import json
import os
from pathlib import Path

def process_latest_image():
    print("\nSmugMug Latest Image Test")
    print("========================\n")
    
    # Load credentials
    config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
    with open(config_file) as f:
        tokens = json.load(f)
    
    # Setup SmugMug client
    api_key = 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq'
    api_secret = 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR'
    
    smugmug = OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=tokens['access_token'],
        resource_owner_secret=tokens['access_token_secret']
    )
    
    # Get user info
    print("Connecting to SmugMug...")
    response = smugmug.get(
        'https://api.smugmug.com/api/v2!authuser',
        headers={'Accept': 'application/json'}
    )
    
    user_data = response.json()
    nickname = user_data['Response']['User']['NickName']
    print(f"Connected as: {nickname}")
    
    # Get latest image
    print("\nFetching recent images...")
    response = smugmug.get(
        f'https://api.smugmug.com/api/v2/user/{nickname}!recentimages',
        headers={'Accept': 'application/json'}
    )
    
    data = response.json()
    if 'Response' not in data:
        print("No response from SmugMug API")
        return
        
    if 'Image' not in data['Response']:
        print("No images found in response")
        print("Available keys:", data['Response'].keys())
        return
        
    images = data['Response']['Image']
    if not images:
        print("No recent images found")
        return
    
    # Get the latest image
    image = images[0]
    print(f"\nProcessing latest image:")
    print(f"Filename: {image['FileName']}")
    print(f"Upload Date: {image['DateTimeUploaded']}")
    print(f"Original Size: {image.get('OriginalSize', 'unknown')} bytes")
    
    # Get archived URL for full resolution
    image_url = image.get('ArchivedUri')
    if not image_url:
        print("Could not find full resolution URL")
        return
    
    print(f"\nImage URL: {image_url}")
    
    # Setup Google Vision
    print("\nGetting AI tags...")
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json")
    vision_client = vision.ImageAnnotatorClient()
    
    # Create vision image
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    # Get labels
    response = vision_client.label_detection(image=vision_image)
    labels = response.label_annotations
    
    # Show tags
    print("\nGoogle Vision Tags:")
    print("-----------------")
    new_tags = []
    for label in labels:
        confidence = label.score * 100
        tag = label.description.lower()
        new_tags.append(tag)
        print(f"- {tag:<30} ({confidence:.1f}% confidence)")
    
    # Get existing keywords
    existing_keywords = set(image.get('Keywords', '').split(',')) if image.get('Keywords') else set()
    existing_keywords.discard('')
    
    print(f"\nExisting Keywords:")
    print("----------------")
    if existing_keywords:
        for keyword in sorted(existing_keywords):
            print(f"- {keyword}")
    else:
        print("None")
    
    # Update image
    print("\nUpdating image with new tags...")
    all_tags = existing_keywords.union(new_tags)
    
    update_response = smugmug.patch(
        f"https://api.smugmug.com{image['Uri']}",
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
        json={'Keywords': ','.join(all_tags)}
    )
    
    if update_response.status_code == 200:
        print("\n✓ Successfully updated image!")
        print(f"Added {len(new_tags)} new tags")
        print("\nView the updated image here:")
        print(image['WebUri'])
    else:
        print(f"\n✗ Failed to update image: {update_response.status_code}")
        print(f"Error: {update_response.text}")

if __name__ == "__main__":
    try:
        process_latest_image()
    except Exception as e:
        print(f"\nError: {str(e)}")
    print("\nPress Enter to exit...")
    input()