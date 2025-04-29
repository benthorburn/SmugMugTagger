from flask import Flask, request, jsonify, render_template
import json
import os
import logging
import traceback
from pathlib import Path
import tempfile
from requests_oauthlib import OAuth1Session
from google.cloud import vision
from urllib.parse import urlparse
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

def get_path_from_url(url):
    """Extract path from SmugMug URL"""
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith('/app/organize'):
        path = path.replace('/app/organize', '', 1)
    return path.rstrip('/')

def get_vision_tags(vision_client, image_url, threshold=20):
    """Get comprehensive tags using multiple Vision API features with enhanced sensitivity"""
    logger.debug(f"Starting Vision analysis on: {image_url}")
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    all_tags = set()
    confidence_scores = {}
    
    try:
        # Use only essential Vision API services to avoid timeout
        
        # 1. Landmark Detection with lower threshold
        logger.debug("Detecting landmarks (with higher sensitivity)...")
        try:
            landmark_response = vision_client.landmark_detection(image=vision_image)
            for landmark in landmark_response.landmark_annotations:
                # 20% threshold for landmarks
                if landmark.score * 100 >= 20:
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
                                elif 57 < lat < 58:  # Central Scotland
                                    all_tags.add('central scotland')
        except Exception as e:
            logger.error(f"Error in landmark detection: {str(e)}")
        
        # 2. Web Detection for better landmark recognition - most effective for landmarks
        logger.debug("Running web detection for better landmark recognition...")
        try:
            web_response = vision_client.web_detection(image=vision_image)
            
            if web_response.web_detection:
                # Best guess labels often identify landmarks better
                for label in web_response.web_detection.best_guess_labels:
                    label_lower = label.label.lower()
                    all_tags.add(label_lower)
                    confidence_scores[f"web_{label_lower}"] = "web match"
                
                # Web entities with 20% threshold
                for entity in web_response.web_detection.web_entities:
                    if entity.score >= 0.2:  # 20% threshold for web entities
                        entity_lower = entity.description.lower()
                        all_tags.add(entity_lower)
                        confidence_scores[f"web_{entity_lower}"] = f"{entity.score * 100:.1f}%"
        except Exception as e:
            logger.error(f"Error in web detection: {str(e)}")
        
        # 3. Label Detection - essential for scene context
        logger.debug("Analyzing general content...")
        try:
            label_response = vision_client.label_detection(image=vision_image)
            for label in label_response.label_annotations:
                if label.score * 100 >= threshold:
                    label_lower = label.description.lower()
                    all_tags.add(label_lower)
                    confidence_scores[label_lower] = f"{label.score * 100:.1f}%"
        except Exception as e:
            logger.error(f"Error in label detection: {str(e)}")
        
        # 4. People Detection via Face Detection (lightweight)
        logger.debug("Detecting people...")
        try:
            face_response = vision_client.face_detection(image=vision_image)
            if face_response.face_annotations:
                all_tags.add('people')
                if len(face_response.face_annotations) > 1:
                    all_tags.add('group photo')
                
                # Add activity context if applicable
                if any(tag in all_tags for tag in ['kayak', 'boat', 'canoe']):
                    all_tags.add('kayaking')
                    all_tags.add('water activity')
                
                if any(tag in all_tags for tag in ['mountain', 'hill', 'hiking']):
                    all_tags.add('hiking')
        except Exception as e:
            logger.error(f"Error in face detection: {str(e)}")
        
        # Add AutoTagged marker
        all_tags.add('AutoTagged')
        
        logger.debug(f"Vision analysis complete. Found {len(all_tags)} tags.")
        return list(all_tags), confidence_scores
        
    except Exception as e:
        logger.error(f"Error in Vision API detection: {str(e)}")
        logger.error(traceback.format_exc())
        return [], {}

@app.route('/')
def index():
    """Render the main page with improved UI"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """Process the album URL and threshold from the form"""
    debug_info = []
    temp_file_path = None
    
    try:
        url = request.form.get('album_url')
        threshold = float(request.form.get('threshold', 20))
        
        debug_info.append(f"Processing URL: {url}")
        debug_info.append(f"Threshold: {threshold}")
        
        if not url:
            return jsonify({"error": "No URL provided", "debug": debug_info})
        
        # Check if credentials are configured
        has_smugmug = bool(os.environ.get('SMUGMUG_TOKENS'))
        has_vision = bool(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        debug_info.append(f"Has SmugMug credentials: {has_smugmug}")
        debug_info.append(f"Has Vision credentials: {has_vision}")
        
        if not has_smugmug or not has_vision:
            return jsonify({"error": "Missing API credentials", "debug": debug_info})
        
        # Process the album
        try:
            # Load SmugMug credentials from environment
            debug_info.append("Loading SmugMug credentials...")
            if os.environ.get('SMUGMUG_TOKENS'):
                tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
                debug_info.append("Loaded SmugMug tokens from environment")
            else:
                # Fallback to file for local development
                config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
                with open(config_file) as f:
                    tokens = json.load(f)
                debug_info.append("Loaded SmugMug tokens from file")
            
            # Setup SmugMug client
            debug_info.append("Setting up SmugMug client...")
            api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
            api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
            
            smugmug = OAuth1Session(
                api_key,
                client_secret=api_secret,
                resource_owner_key=tokens['access_token'],
                resource_owner_secret=tokens['access_token_secret']
            )
            debug_info.append("SmugMug client initialized successfully")
            
            # Setup Google Cloud Vision client
            debug_info.append("Setting up Google Cloud Vision client...")
            temp_file = None
            
            if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
                # Create a persistent file for the entire process
                debug_info.append("Using Google credentials from environment")
                credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
                temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
                temp_file.write(credentials_json)
                temp_file.close()
                temp_file_path = temp_file.name
                debug_info.append(f"Created credentials file at: {temp_file_path}")
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_file_path
            else:
                # Fallback to file for local development
                debug_info.append("Using Google credentials from file")
                creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
            
            # Create Vision client
            vision_client = vision.ImageAnnotatorClient()
            debug_info.append("Vision client initialized successfully")
            
            # Get user info
            debug_info.append("Getting user info...")
            response = smugmug.get(
                'https://api.smugmug.com/api/v2!authuser',
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code != 200:
                debug_info.append(f"Error getting user info - Status code: {response.status_code}")
                debug_info.append(f"Response: {response.text}")
                return jsonify({"error": "Failed to authenticate with SmugMug", "debug": debug_info})
            
            user_data = response.json()['Response']['User']
            nickname = user_data['NickName']
            debug_info.append(f"Authenticated as: {nickname}")
            
            # Extract album path
            album_path = get_path_from_url(url)
            debug_info.append(f"Extracted album path: {album_path}")
            
            # Get album info
            debug_info.append(f"Looking up album...")
            response = smugmug.get(
                f'https://api.smugmug.com/api/v2/user/{nickname}!urlpathlookup',
                params={'urlpath': album_path},
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code != 200:
                debug_info.append(f"Error looking up album - Status code: {response.status_code}")
                debug_info.append(f"Response: {response.text}")
                return jsonify({"error": "Failed to find album", "debug": debug_info})
            
            response_data = response.json()['Response']
            debug_info.append(f"Response keys: {list(response_data.keys())}")
            
            # Check if we found an album
            if 'Album' not in response_data:
                debug_info.append("No album found in response")
                return jsonify({"error": "Album not found", "debug": debug_info})
            
            album_data = response_data['Album']
            album_key = album_data['AlbumKey']
            album_name = album_data['Name']
            debug_info.append(f"Found album: '{album_name}' with key: {album_key}")
            
            # Get images
            debug_info.append("Getting images from album...")
            response = smugmug.get(
                f'https://api.smugmug.com/api/v2/album/{album_key}!images',
                params={
                    '_filter': 'ImageKey,FileName,ThumbnailUrl,ArchivedUri,WebUri,KeywordArray'
                },
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code != 200:
                debug_info.append(f"Error getting images - Status code: {response.status_code}")
                debug_info.append(f"Response: {response.text}")
                return jsonify({"error": "Failed to get album images", "debug": debug_info})
            
            response_data = response.json()['Response']
            images = response_data.get('AlbumImage', [])
            debug_info.append(f"Found {len(images)} images in the album")
            
            if not images:
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        debug_info.append("Cleaned up temporary credentials file")
                    except Exception as e:
                        debug_info.append(f"Error removing temp file: {str(e)}")
                        
                return jsonify({
                    "success": True,
                    "message": "No images found in the album",
                    "totalImages": 0,
                    "albumUrl": album_data['WebUri'],
                    "debug": debug_info
                })
            
            # Process images in smaller batches with more time between batches
            batch_size = 2  # Fixed at 2 to avoid timeouts
            processed_images = []
            failed_images = []
            
            debug_info.append(f"Processing images in batches of {batch_size}...")
            
            # Only process the first N images to avoid timeout
            max_images_per_request = min(6, len(images))
            debug_info.append(f"Limiting to {max_images_per_request} images per request to avoid timeout")
            
            for i in range(0, max_images_per_request, batch_size):
                batch = images[i:i+batch_size]
                debug_info.append(f"Processing batch {i//batch_size + 1}/{(max_images_per_request-1)//batch_size + 1} ({len(batch)} images)")
                
                for image in batch:
                    try:
                        # Check if already tagged
                        current_keywords = image.get('KeywordArray', [])
                        if current_keywords and 'AutoTagged' in current_keywords:
                            debug_info.append(f"Image {image.get('FileName', 'Unknown')} already tagged, skipping")
                            continue
                        
                        # Get image URLs
                        image_key = f"{image['ImageKey']}-0"
                        image_url = image.get('ArchivedUri') or image.get('WebUri')
                        thumbnail_url = image.get('ThumbnailUrl')
                        
                        if not image_url:
                            debug_info.append(f"No image URL found for {image.get('FileName', 'Unknown')}, skipping")
                            failed_images.append(image.get('FileName', 'Unknown'))
                            continue
                        
                        # Get Vision AI tags
                        debug_info.append(f"Getting Vision AI tags for {image.get('FileName', 'Unknown')}")
                        vision_tags, confidence_scores = get_vision_tags(vision_client, image_url, threshold)
                        
                        if not vision_tags:
                            debug_info.append(f"No tags returned from Vision API for {image.get('FileName', 'Unknown')}, skipping")
                            failed_images.append(image.get('FileName', 'Unknown'))
                            continue
                        
                        # Ensure current_keywords is a list
                        if current_keywords is None:
                            current_keywords = []
                        elif isinstance(current_keywords, str):
                            current_keywords = [current_keywords]
                        
                        # Filter out empty tags
                        vision_tags = [tag for tag in vision_tags if tag.strip()]
                        
                        # Combine with existing tags
                        all_tags = list(dict.fromkeys(current_keywords + vision_tags))
                        debug_info.append(f"Combined {len(all_tags)} tags for {image.get('FileName', 'Unknown')}")
                        
                        # Update the image
                        debug_info.append(f"Updating image {image_key}")
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
                        
                        if base_response.status_code != 200:
                            debug_info.append(f"Error updating base image: {base_response.status_code}")
                            error_text = base_response.text
                            if len(error_text) > 500:
                                error_text = error_text[:500] + "..."
                            debug_info.append(f"Response: {error_text}")
                            failed_images.append(image.get('FileName', 'Unknown'))
                            continue
                        
                        # Success
                        debug_info.append(f"Successfully tagged image {image.get('FileName', 'Unknown')}")
                        processed_images.append({
                            'filename': image.get('FileName', 'Unknown'),
                            'keywords': all_tags,
                            'thumbnailUrl': thumbnail_url
                        })
                        
                    except Exception as e:
                        error_trace = traceback.format_exc()
                        debug_info.append(f"Error processing image: {str(e)}")
                        debug_info.append(f"Error trace: {error_trace}")
                        failed_images.append(image.get('FileName', 'Unknown'))
                
                # Longer pause between batches to allow memory cleanup and avoid timeouts
                time.sleep(3)
            
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    debug_info.append("Cleaned up temporary credentials file")
                except Exception as e:
                    debug_info.append(f"Error removing temp file: {str(e)}")
            
            remaining_images = len(images) - max_images_per_request
            message = f"Processing complete: {len(processed_images)} images tagged successfully, {len(failed_images)} failed"
            if remaining_images > 0:
                message += f". Note: {remaining_images} images were skipped to avoid timeout. Consider processing the album in multiple batches."
            
            return jsonify({
                "success": True,
                "message": message,
                "processedImages": processed_images,
                "failedImages": failed_images,
                "totalImages": len(images),
                "processedCount": len(processed_images),
                "failedCount": len(failed_images),
                "skippedCount": remaining_images,
                "albumUrl": album_data['WebUri'],
                "debug": debug_info
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            debug_info.append(f"Processing error: {str(e)}")
            debug_info.append(f"Error trace: {error_traceback}")
            
            # Clean up temp file if it exists
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    debug_info.append("Cleaned up temporary credentials file")
                except Exception as clean_e:
                    debug_info.append(f"Error removing temp file: {str(clean_e)}")
                    
            return jsonify({"error": str(e), "debug": debug_info})
    
    except Exception as e:
        error_traceback = traceback.format_exc()
        debug_info.append(f"Top-level error: {str(e)}")
        debug_info.append(f"Error trace: {error_traceback}")
        
        # Clean up temp file if it exists
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                debug_info.append("Cleaned up temporary credentials file")
            except Exception as clean_e:
                debug_info.append(f"Error removing temp file: {str(clean_e)}")
                
        return jsonify({"error": str(e), "debug": debug_info})

@app.route('/test-credentials')
def test_credentials():
    """Test if credentials are working properly"""
    results = {
        "smugmug": {"status": "not_tested", "details": "Not tested yet"},
        "vision": {"status": "not_tested", "details": "Not tested yet"}
    }
    
    # Test SmugMug
    try:
        if os.environ.get('SMUGMUG_TOKENS'):
            tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
            
            # Check if tokens look valid
            if not 'access_token' in tokens or not 'access_token_secret' in tokens:
                results["smugmug"] = {
                    "status": "invalid",
                    "details": "Tokens missing required fields"
                }
            else:
                # Try to connect
                api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
                api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
                
                smugmug = OAuth1Session(
                    api_key,
                    client_secret=api_secret,
                    resource_owner_key=tokens['access_token'],
                    resource_owner_secret=tokens['access_token_secret']
                )
                
                response = smugmug.get(
                    'https://api.smugmug.com/api/v2!authuser',
                    headers={'Accept': 'application/json'}
                )
                
                if response.status_code == 200:
                    user_data = response.json()['Response']['User']
                    results["smugmug"] = {
                        "status": "working",
                        "details": f"Connected as: {user_data.get('NickName', 'Unknown')}"
                    }
                else:
                    results["smugmug"] = {
                        "status": "error",
                        "details": f"API returned status {response.status_code}: {response.text}"
                    }
        else:
            results["smugmug"] = {
                "status": "missing",
                "details": "SmugMug tokens not configured"
            }
    except Exception as e:
        results["smugmug"] = {
            "status": "error",
            "details": f"Error testing SmugMug credentials: {str(e)}"
        }
    
    # Test Vision
    try:
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
            creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            
            # Check if JSON is valid
            try:
                json.loads(creds_json)
                
                # Try to initialize client
                temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
                temp_file.write(creds_json)
                temp_file.close()
                credentials_path = temp_file.name
                
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                
                try:
                    vision_client = vision.ImageAnnotatorClient()
                    
                    # Test with a simple operation
                    test_image = vision.Image()
                    test_image.source.image_uri = "https://storage.googleapis.com/cloud-samples-data/vision/face/faces.jpeg"
                    test_response = vision_client.label_detection(image=test_image)
                    
                    if len(test_response.label_annotations) > 0:
                        results["vision"] = {
                            "status": "working",
                            "details": f"Successfully detected {len(test_response.label_annotations)} labels in test image"
                        }
                    else:
                        results["vision"] = {
                            "status": "working",
                            "details": "Vision client initialized but no labels detected"
                        }
                    
                except Exception as e:
                    results["vision"] = {
                        "status": "error",
                        "details": f"Error using Vision client: {str(e)}"
                    }
                
                # Clean up
                os.unlink(credentials_path)
                
            except json.JSONDecodeError:
                results["vision"] = {
                    "status": "invalid",
                    "details": "Invalid JSON format in credentials"
                }
        else:
            results["vision"] = {
                "status": "missing",
                "details": "Google Vision credentials not configured"
            }
    except Exception as e:
        results["vision"] = {
            "status": "error",
            "details": f"Error testing Vision credentials: {str(e)}"
        }
    
    return jsonify(results)

@app.route('/diagnostic')
def diagnostic():
    """Render diagnostic page"""
    return render_template('diagnostic.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
