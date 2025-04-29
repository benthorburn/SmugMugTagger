from requests_oauthlib import OAuth1Session
import json
from pathlib import Path
import time
from google.cloud import vision
import os
from urllib.parse import urlparse

def get_path_from_url(url):
    """Extract path from SmugMug URL"""
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith('/app/organize'):
        path = path.replace('/app/organize', '', 1)
    return path.rstrip('/')

def get_vision_tags(vision_client, image_url):
    """Get comprehensive tags using multiple Vision API features"""
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    all_tags = set()
    confidence_scores = {}
    
    try:
        # 1. Label Detection (general objects, scenes, activities)
        print("Analyzing general content...")
        label_response = vision_client.label_detection(image=vision_image)
        for label in label_response.label_annotations:
            if label.score * 100 >= 30:
                label_lower = label.description.lower()
                all_tags.add(label_lower)
                confidence_scores[label_lower] = f"{label.score * 100:.1f}%"
        
        # 2. Object Detection (specific objects with locations)
        print("Detecting specific objects...")
        object_response = vision_client.object_localization(image=vision_image)
        for obj in object_response.localized_object_annotations:
            if obj.score * 100 >= 30:
                obj_name = obj.name.lower()
                all_tags.add(obj_name)
                confidence_scores[obj_name] = f"{obj.score * 100:.1f}%"
        
        # 3. Landmark Detection with full location data
        print("Detecting landmarks and locations...")
        landmark_response = vision_client.landmark_detection(image=vision_image)
        for landmark in landmark_response.landmark_annotations:
            if landmark.score * 100 >= 30:
                # Add landmark name
                landmark_name = landmark.description.lower()
                all_tags.add(landmark_name)
                confidence_scores[landmark_name] = f"{landmark.score * 100:.1f}%"
                
                # Add location data if available
                for location in landmark.locations:
                    if location.lat_lng:
                        lat = location.lat_lng.latitude
                        lng = location.lat_lng.longitude
                        
                        # Add Scotland-specific location tags
                        if 56 < lat < 59:  # Scotland
                            all_tags.add('scotland')
                            if lat > 58:  # Northern Scotland
                                all_tags.add('northern scotland')
                                if lng < -4:  # Northwest
                                    all_tags.add('northwest highlands')
                                    all_tags.add('west coast')
                                elif lng > -3:  # Northeast
                                    all_tags.add('northeast scotland')
                                    all_tags.add('east coast')
                            elif 57 < lat < 58:  # Central Scotland
                                all_tags.add('central scotland')
                            if lng < -5:  # Western Scotland
                                all_tags.add('western scotland')
                            elif lng > -3:  # Eastern Scotland
                                all_tags.add('eastern scotland')
        
        # 4. Text Detection (OCR for signs and plaques)
        print("Reading text and signs...")
        text_response = vision_client.text_detection(image=vision_image)
        if text_response.text_annotations:
            # Get all detected text
            full_text = text_response.text_annotations[0].description.lower()
            
            # Add individual words/phrases as tags if they appear meaningful
            words = set(full_text.split())
            for word in words:
                if len(word) > 2:  # Ignore very short words
                    all_tags.add(word)
            
            # Store the full text for context
            if full_text:
                all_tags.add('text_present')
                confidence_scores['detected_text'] = full_text
# 5. Web Detection (similar images and metadata)
        print("Analyzing web context...")
        web_response = vision_client.web_detection(image=vision_image)
        web_detection = web_response.web_detection
        
        if web_detection:
            # Best guess labels from similar images
            for label in web_detection.best_guess_labels:
                label_lower = label.label.lower()
                all_tags.add(label_lower)
                confidence_scores[f"web_{label_lower}"] = "web match"
            
            # Web entities (concepts associated with the image)
            for entity in web_detection.web_entities:
                if entity.score >= 0.3:  # 30% confidence threshold
                    entity_lower = entity.description.lower()
                    all_tags.add(entity_lower)
                    confidence_scores[f"web_{entity_lower}"] = f"{entity.score * 100:.1f}%"
            
            # Page titles and descriptions from similar images
            for page in web_detection.pages_with_matching_images:
                if page.page_title:
                    # Extract meaningful keywords from page titles
                    title_words = page.page_title.lower().split()
                    for word in title_words:
                        if len(word) > 3:  # Ignore very short words
                            all_tags.add(word)
        
        # 6. Image Properties Detection (colors, brightness)
        print("Analyzing image properties...")
        property_response = vision_client.image_properties(image=vision_image)
        if property_response.image_properties_annotation:
            colors = property_response.image_properties_annotation.dominant_colors.colors
            
            # Analyze overall brightness and colors
            bright_colors = 0
            dark_colors = 0
            blue_sky = False
            green_nature = False
            
            for color in colors[:3]:  # Look at top 3 dominant colors
                rgb_sum = color.color.red + color.color.green + color.color.blue
                
                # Brightness analysis
                if rgb_sum > 600:  # Bright color
                    bright_colors += 1
                elif rgb_sum < 300:  # Dark color
                    dark_colors += 1
                
                # Sky detection
                if (color.color.blue > 200 and 
                    color.color.blue > color.color.red and 
                    color.color.blue > color.color.green):
                    blue_sky = True
                
                # Nature/vegetation detection
                if (color.color.green > 150 and 
                    color.color.green > color.color.red and 
                    color.color.green > color.color.blue):
                    green_nature = True
            
            # Add lighting condition tags
            if bright_colors >= 2:
                all_tags.add('bright')
                all_tags.add('well lit')
            elif dark_colors >= 2:
                all_tags.add('dark')
                all_tags.add('low light')
            
            # Add color-based environment tags
            if blue_sky:
                all_tags.add('blue sky')
                all_tags.add('clear sky')
            if green_nature:
                all_tags.add('verdant')
                all_tags.add('greenery')
        
        # 7. Face Detection
        print("Analyzing people and expressions...")
        face_response = vision_client.face_detection(image=vision_image)
        if face_response.face_annotations:
            all_tags.add('people')
            confidence_scores['people'] = '100%'
            
            face_count = len(face_response.face_annotations)
            if face_count > 1:
                all_tags.add('group photo')
                if face_count > 4:
                    all_tags.add('group activity')
            
            for face in face_response.face_annotations:
                # Expression detection
                if face.joy_likelihood >= vision.Likelihood.LIKELY:
                    all_tags.add('smiling')
                if face.headwear_likelihood >= vision.Likelihood.LIKELY:
                    all_tags.add('headwear')
        
        # Clean up and normalize tags
        cleaned_tags = set()
        for tag in all_tags:
            # Remove any special characters and extra spaces
            cleaned_tag = ' '.join(tag.split())
            if cleaned_tag:  # Only add non-empty tags
                cleaned_tags.add(cleaned_tag)
        
        return sorted(list(cleaned_tags)), confidence_scores
        
    except Exception as e:
        print(f"Error in Vision API detection: {str(e)}")
        return [], {}
def test_album_tag_writing():
    print("\nSmugMug Album Tag Writing Test")
    print("============================\n")
    
    # Get album URL from user
    print("Please paste the SmugMug album URL:")
    print("(e.g., https://username.smugmug.com/Album-Name)")
    album_url = input("> ").strip()
    
    if not album_url:
        print("No URL provided. Exiting...")
        return
        
    album_path = get_path_from_url(album_url)
    print(f"\nExtracted path: {album_path}")
    
    # Confirm with user
    print("\nIs this the correct path? (y/n)")
    if input("> ").lower() != 'y':
        print("Operation cancelled.")
        return
    
    try:
        # Load SmugMug credentials
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
        
        # Setup Google Cloud Vision client
        creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
        vision_client = vision.ImageAnnotatorClient()
        
        print(f"\nLooking up album: {album_path}")
        
        # Get user info
        response = smugmug.get(
            'https://api.smugmug.com/api/v2!authuser',
            headers={'Accept': 'application/json'}
        )
        user_data = response.json()['Response']['User']
        nickname = user_data['NickName']
        
        # Get album info
        response = smugmug.get(
            f'https://api.smugmug.com/api/v2/user/{nickname}!urlpathlookup',
            params={'urlpath': album_path},
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            print(f"Error finding album: {response.status_code}")
            print(response.text)
            return
        
        album_data = response.json()['Response']['Album']
        album_key = album_data['AlbumKey']
        print(f"\nFound album: {album_data['Name']}")
        
        # Get images
        print("\nFetching album images...")
        response = smugmug.get(
            f'https://api.smugmug.com/api/v2/album/{album_key}!images',
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            print(f"Error getting images: {response.status_code}")
            print(response.text)
            return
        
        images = response.json()['Response'].get('AlbumImage', [])
        total_images = len(images)
        print(f"Found {total_images} images")
        
        if total_images > 20:
            print(f"\nWarning: This album contains {total_images} images.")
            print("Processing may take some time.")
            print("Do you want to continue? (y/n)")
            if input("> ").lower() != 'y':
                print("Operation cancelled.")
                return
        
        # Process images
        successful = 0
        skipped = 0
        failed = 0
        
        for index, image in enumerate(images, 1):
            print(f"\nProcessing image {index}/{total_images}")
            print(f"Filename: {image['FileName']}")
            
            try:
                # Show current keywords
                current_keywords = image.get('KeywordArray', [])
                print("\nCurrent keywords:", end=" ")
                if current_keywords:
                    print(", ".join(current_keywords))
                else:
                    print("None")
                
                # Check if already processed
                if 'AutoTagged' in current_keywords:
                    print("✓ Image already processed (found AutoTagged keyword)")
                    skipped += 1
                    continue
                
                image_key = f"{image['ImageKey']}-0"
                
                # Get image URL for Vision API
                image_url = image.get('ArchivedUri') or image.get('WebUri')
                if not image_url:
                    print("✗ No image URL found - skipping")
                    failed += 1
                    continue
                
                # Get Vision AI tags
                print("\nAnalyzing image with Vision AI...")
                vision_tags, confidence_scores = get_vision_tags(vision_client, image_url)
                
                if vision_tags:
                    print("\nVision AI suggested tags:")
                    for tag in sorted(vision_tags):
                        confidence = confidence_scores.get(tag, 'N/A')
                        print(f"- {tag} ({confidence})")
                        
                    # Print any detected text
                    if 'detected_text' in confidence_scores:
                        print("\nDetected text:")
                        print(confidence_scores['detected_text'])
                else:
                    print("✗ No tags found - skipping")
                    failed += 1
                    continue
                
                # Add AutoTagged marker
                vision_tags.append('AutoTagged')
                
                # Combine tags
                all_tags = list(dict.fromkeys(current_keywords + vision_tags))
                
                print("\nFinal combined tags:")
                for tag in sorted(all_tags):
                    confidence = confidence_scores.get(tag, 'N/A')
                    if confidence != 'N/A':
                        print(f"- {tag} ({confidence})")
                    else:
                        print(f"- {tag}")
                
                # Update image
                update_data = {
                    'KeywordArray': all_tags,
                    'ShowKeywords': True
                }
                
                # Update base image
                print("\nUpdating base image...")
                base_response = smugmug.patch(
                    f'https://api.smugmug.com/api/v2/image/{image_key}',
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    },
                    json=update_data
                )
                
                if base_response.status_code != 200:
                    print(f"✗ Base image update failed: {base_response.status_code}")
                    print(base_response.text)
                    failed += 1
                    continue
                
                # Update album image
                print("Updating album image...")
                album_response = smugmug.patch(
                    f"https://api.smugmug.com/api/v2/album/{album_key}/image/{image_key}",
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    },
                    json=update_data
                )
                
                if album_response.status_code != 200:
                    print(f"✗ Album image update failed: {album_response.status_code}")
                    print(album_response.text)
                    failed += 1
                    continue
                
                print("✓ Successfully updated image")
                successful += 1
                
                # Brief pause between images
                time.sleep(1)
                
            except Exception as e:
                print(f"✗ Error processing image: {str(e)}")
                failed += 1
                continue
        
        # Final summary
        print("\n=== Processing Complete ===")
        print(f"Total images: {total_images}")
        print(f"Successfully processed: {successful}")
        print(f"Already processed (skipped): {skipped}")
        print(f"Failed: {failed}")
        print(f"\nView album here: {album_data['WebUri']}")
        
    except Exception as e:
        print(f"\nError in main process: {str(e)}")

if __name__ == "__main__":
    try:
        test_album_tag_writing()
    except Exception as e:
        print(f"\nError: {str(e)}")
    print("\nPress Enter to exit...")
    input()