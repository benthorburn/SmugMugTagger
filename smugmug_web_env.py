from requests_oauthlib import OAuth1Session
import json
from pathlib import Path
import time
from google.cloud import vision
import os
from urllib.parse import urlparse
import sys
import logging

# Configure logging
logging.basicConfig(filename='smugmug_debug.log', level=logging.DEBUG)

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
        logging.debug("Analyzing general content...")
        label_response = vision_client.label_detection(image=vision_image)
        for label in label_response.label_annotations:
            if label.score * 100 >= 30:
                label_lower = label.description.lower()
                all_tags.add(label_lower)
                confidence_scores[label_lower] = f"{label.score * 100:.1f}%"
        
        # 2. Object Detection
        logging.debug("Detecting specific objects...")
        object_response = vision_client.object_localization(image=vision_image)
        for obj in object_response.localized_object_annotations:
            if obj.score * 100 >= 30:
                obj_name = obj.name.lower()
                all_tags.add(obj_name)
                confidence_scores[obj_name] = f"{obj.score * 100:.1f}%"
        
        # 3. Landmark Detection
        logging.debug("Detecting landmarks...")
        landmark_response = vision_client.landmark_detection(image=vision_image)
        for landmark in landmark_response.landmark_annotations:
            if landmark.score * 100 >= 30:
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
        
        # 4. Text Detection (OCR)
        logging.debug("Reading text and signs...")
        text_response = vision_client.text_detection(image=vision_image)
        if text_response.text_annotations:
            full_text = text_response.text_annotations[0].description.lower()
            words = set(full_text.split())
            for word in words:
                if len(word) > 2:  # Skip very short words
                    if hasattr(text_response.text_annotations[0], 'confidence'):
                        confidence = text_response.text_annotations[0].confidence * 100
                        if confidence >= 45:  # 45% threshold for text
                            all_tags.add(word)
                            confidence_scores[f"text_{word}"] = f"{confidence:.1f}%"
            if words:
                all_tags.add('text_present')

        # 5. Web Detection
        logging.debug("Analyzing web context...")
        web_response = vision_client.web_detection(image=vision_image)
        if web_response.web_detection:
            # Best guess labels
            for label in web_response.web_detection.best_guess_labels:
                label_lower = label.label.lower()
                all_tags.add(label_lower)
                confidence_scores[f"web_{label_lower}"] = "web match"
            
            # Web entities
            for entity in web_response.web_detection.web_entities:
                if entity.score >= 0.3:  # 30% threshold
                    entity_lower = entity.description.lower()
                    all_tags.add(entity_lower)
                    confidence_scores[f"web_{entity_lower}"] = f"{entity.score * 100:.1f}%"

        # 6. Image Properties
        logging.debug("Analyzing image properties...")
        property_response = vision_client.image_properties(image=vision_image)
        if property_response.image_properties_annotation:
            colors = property_response.image_properties_annotation.dominant_colors.colors
            
            # Analyze colors if they make up at least 60% of the image
            bright_colors = 0
            dark_colors = 0
            nature_colors = 0
            
            for color in colors[:3]:  # Look at top 3 dominant colors
                if color.score >= 0.6:  # 60% threshold
                    rgb_sum = color.color.red + color.color.green + color.color.blue
                    
                    # Brightness analysis
                    if rgb_sum > 600:
                        bright_colors += 1
                    elif rgb_sum < 300:
                        dark_colors += 1
                    
                    # Color-based environment detection
                    if (color.color.blue > 200 and 
                        color.color.blue > color.color.red and 
                        color.color.blue > color.color.green):
                        all_tags.add('blue sky')
                        confidence_scores['blue sky'] = f"{color.score * 100:.1f}%"
                    
                    elif (color.color.green > 150 and 
                          color.color.green > color.color.red and 
                          color.color.green > color.color.blue):
                        nature_colors += 1
            
            # Add summary color tags
            if bright_colors >= 2:
                all_tags.add('bright')
                all_tags.add('well lit')
            elif dark_colors >= 2:
                all_tags.add('dark')
                all_tags.add('low light')
            
            if nature_colors >= 2:
                all_tags.add('verdant')
                all_tags.add('greenery')

        # 7. Face Detection
        logging.debug("Analyzing people and expressions...")
        face_response = vision_client.face_detection(image=vision_image)
        if face_response.face_annotations:
            faces = face_response.face_annotations
            if len(faces) > 0:  # If any faces detected with 30% confidence
                face_confidence = min(face.detection_confidence for face in faces)
                if face_confidence >= 0.3:
                    all_tags.add('people')
                    confidence_scores['people'] = f"{face_confidence * 100:.1f}%"
                    
                    if len(faces) > 1:
                        all_tags.add('group photo')
                        if len(faces) > 4:
                            all_tags.add('group activity')
                    
                    # Expression detection
                    joy_detected = any(face.joy_likelihood >= vision.Likelihood.LIKELY for face in faces)
                    if joy_detected:
                        all_tags.add('smiling')
                        all_tags.add('happy')
                    
                    # Check for outdoor/activity context
                    if 'outdoor' in all_tags or 'nature' in all_tags:
                        all_tags.add('people outdoors')
                        if len(faces) > 1:
                            all_tags.add('group outdoors')
        
        return list(all_tags), confidence_scores
        
    except Exception as e:
        logging.error(f"Error in Vision API detection: {str(e)}")
        return [], {}

def test_album_tag_writing(url, threshold=30):
    try:
        # Load SmugMug credentials - first try environment variables
        if os.environ.get('SMUGMUG_TOKENS'):
            tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
            logging.debug("Using SmugMug tokens from environment variables")
        else:
            # Fallback to file for local development
            config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
            with open(config_file) as f:
                tokens = json.load(f)
                logging.debug("Using SmugMug tokens from file")
        
        # Setup SmugMug client
        api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
        api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
        
        smugmug = OAuth1Session(
            api_key,
            client_secret=api_secret,
            resource_owner_key=tokens['access_token'],
            resource_owner_secret=tokens['access_token_secret']
        )

        # Setup Google Cloud Vision client
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
            # Use environment variable for credentials
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            credentials_path = 'google_credentials_temp.json'
            with open(credentials_path, 'w') as f:
                f.write(credentials_json)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            vision_client = vision.ImageAnnotatorClient()
            logging.debug("Using Google Vision credentials from environment variables")
        else:
            # Fallback to file for local development
            creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
            vision_client = vision.ImageAnnotatorClient()
            logging.debug("Using Google Vision credentials from file")
        
        album_path = get_path_from_url(url)
        logging.debug(f"Processing album path: {album_path}")
        
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
            return json.dumps({"error": f"Failed to find album: {response.text}"})
        
        album_data = response.json()['Response']['Album']
        album_key = album_data['AlbumKey']
        
        # Get images with expanded details
        response = smugmug.get(
            f'https://api.smugmug.com/api/v2/album/{album_key}!images',
            params={
                '_expand': 'ImageSizes,ImageMetadata',
                '_shorturis': 1,
                '_filter': 'ImageKey,FileName,ThumbnailUrl,ArchivedUri,WebUri,KeywordArray'
            },
            headers={'Accept': 'application/json'}
        )
        
        logging.debug("=== Raw Response ===")
        logging.debug(json.dumps(response.json(), indent=2))
        logging.debug("=== Response Status ===")
        logging.debug(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            return json.dumps({"error": "Failed to get album images"})
        
        images = response.json()['Response'].get('AlbumImage', [])
        logging.debug("=== Images Array ===")
        logging.debug(f"Number of images: {len(images)}")
        
        processed_images = []
        failed_images = []
        
        for image in images:
            try:
                # Check if already processed
                current_keywords = image.get('KeywordArray', [])
                if 'AutoTagged' in current_keywords:
                    continue
                
                image_key = f"{image['ImageKey']}-0"
                image_url = image.get('ArchivedUri') or image.get('WebUri')
                thumbnail_url = image.get('ThumbnailUrl')
                
                if not image_url:
                    failed_images.append(image['FileName'])
                    continue
                
                # Get Vision AI tags with expanded detection
                vision_tags, confidence_scores = get_vision_tags(vision_client, image_url)
                if not vision_tags:
                    failed_images.append(image['FileName'])
                    continue
                
                # Add AutoTagged marker
                vision_tags.append('AutoTagged')
                
                # Combine tags while preserving existing ones
                all_tags = list(dict.fromkeys(current_keywords + vision_tags))
                
                # Update image
                update_data = {
                    'KeywordArray': all_tags,
                    'ShowKeywords': True
                }
                
                # Update base image
                base_response = smugmug.patch(
                    f'https://api.smugmug.com/api/v2/image/{image_key}',
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    },
                    json=update_data
                )
                
                # Update album image
                album_response = smugmug.patch(
                    f'https://api.smugmug.com/api/v2/album/{album_key}/image/{image_key}',
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    },
                    json=update_data
                )
                
                if base_response.status_code == 200 and album_response.status_code == 200:
                    processed_images.append({
                        'filename': image['FileName'],
                        'keywords': all_tags,
                        'confidence': confidence_scores,
                        'thumbnailUrl': thumbnail_url
                    })
                    logging.debug(f"Successfully processed image: {image['FileName']}")
                else:
                    failed_images.append(image['FileName'])
                    logging.error(f"Failed to update image: {image['FileName']}")
                
                # Brief pause between images
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"Error processing image {image.get('FileName', 'unknown')}: {str(e)}")
                failed_images.append(image.get('FileName', 'unknown'))
                continue
        
        result = {
            "success": True,
            "processedImages": processed_images,
            "failedImages": failed_images,
            "totalImages": len(images),
            "successfullyProcessed": len(processed_images),
            "failed": len(failed_images),
            "albumUrl": album_data['WebUri']
        }
        
        return json.dumps(result)

    except Exception as e:
        logging.error(f"Error in main process: {str(e)}")
        return json.dumps({"error": str(e)})
