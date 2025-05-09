from flask import Flask, request, jsonify, render_template, session
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
import re
import hashlib
import datetime
import threading

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key')

# In-memory state cache - will be lost on app restart
# For demonstration purposes - in production, use Redis or database
PROCESS_STATE = {}
# Background processing tasks
BACKGROUND_TASKS = {}

def get_path_from_url(url):
    """Extract path from SmugMug URL"""
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith('/app/organize'):
        path = path.replace('/app/organize', '', 1)
    return path.rstrip('/')

def extract_album_info_from_url(url):
    """Extract album info from various SmugMug URL formats"""
    parsed = urlparse(url)
    path = parsed.path
    
    # Extract username and album path
    parts = path.strip('/').split('/')
    
    if len(parts) <= 1:
        return None, None
    
    # Try to determine username from hostname or first path part
    username = None
    album_path = None
    
    # Check for domain-based username
    domain_parts = parsed.netloc.split('.')
    if len(domain_parts) >= 3 and domain_parts[0] != 'www':
        username = domain_parts[0]
        album_path = '/' + '/'.join(parts)
    else:
        # First part of path might be username
        username = parts[0]
        album_path = '/' + '/'.join(parts[1:])
    
    # Special case for wildernessscotland
    if username and username.lower() == 'wildernessscotland':
        # Try to match /Wilderness-Scotland/... pattern
        if len(parts) > 1 and parts[1].startswith('Wilderness-'):
            album_path = '/' + '/'.join(parts[1:])
    
    return username, album_path

def generate_session_id(album_url, threshold):
    """Generate a unique session ID based on album URL and threshold"""
    source = f"{album_url}:{threshold}:{datetime.datetime.now().strftime('%Y-%m-%d')}"
    return hashlib.md5(source.encode()).hexdigest()

def save_progress(session_id, album_key, album_name, album_url, total_images, 
                 processed_indices, processed_images, failed_images, next_index, is_processing=False):
    """Save processing progress to state cache"""
    PROCESS_STATE[session_id] = {
        'album_key': album_key,
        'album_name': album_name,
        'album_url': album_url,
        'total_images': total_images,
        'processed_indices': list(processed_indices),
        'processed_images': processed_images,
        'failed_images': failed_images,
        'next_index': next_index,
        'last_updated': datetime.datetime.now().isoformat(),
        'is_processing': is_processing  # Flag to indicate if background processing is active
    }
    return PROCESS_STATE[session_id]

def load_progress(session_id):
    """Load processing progress from state cache"""
    return PROCESS_STATE.get(session_id)

def get_vision_tags(vision_client, image_url, threshold=20):
    """Get comprehensive tags using multiple Vision API features with enhanced sensitivity"""
    logger.debug(f"Starting Vision analysis on: {image_url}")
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    all_tags = set()
    confidence_scores = {}
    
    try:
        # Use multiple Vision API services in sequence to maximize tag generation
        
        # 1. Landmark Detection with lower threshold
        logger.debug("Detecting landmarks (with higher sensitivity)...")
        try:
            landmark_response = vision_client.landmark_detection(image=vision_image)
            for landmark in landmark_response.landmark_annotations:
                # 15% threshold for landmarks - lower to catch more
                if landmark.score * 100 >= 15:
                    landmark_name = landmark.description.lower()
                    all_tags.add(landmark_name)
                    confidence_scores[landmark_name] = f"{landmark.score * 100:.1f}%"
                    
                    # Extract country and region info
                    parts = landmark_name.split(',')
                    if len(parts) > 1:
                        for part in parts:
                            part = part.strip().lower()
                            if part and len(part) > 3:  # Avoid too short names
                                all_tags.add(part)
                    
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
                                        all_tags.add('west coast scotland')
                                    elif lng > -3:  # Northeast
                                        all_tags.add('northeast scotland')
                                        all_tags.add('east coast scotland')
                                elif 57 < lat < 58:  # Central Scotland
                                    all_tags.add('central scotland')
                                    if lng < -5:
                                        all_tags.add('western scotland')
                                    elif lng > -3:
                                        all_tags.add('eastern scotland')
                                elif lat < 57:  # Southern Scotland
                                    all_tags.add('southern scotland')
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
                    
                    # Break compound labels into components
                    words = re.findall(r'\b[a-zA-Z]{3,}\b', label_lower)
                    for word in words:
                        if word not in ['and', 'the', 'with', 'from']:
                            all_tags.add(word)
                
                # Web entities with 15% threshold
                for entity in web_response.web_detection.web_entities:
                    if entity.score >= 0.15:  # 15% threshold for web entities
                        entity_lower = entity.description.lower()
                        all_tags.add(entity_lower)
                        confidence_scores[f"web_{entity_lower}"] = f"{entity.score * 100:.1f}%"
                
                # Check page titles and descriptions for Scotland-specific keywords
                scotland_keywords = [
                    'scotland', 'scottish', 'highland', 'hebrides', 'isle', 'skye', 
                    'glen', 'loch', 'ben', 'munro', 'cairn', 'cuillin', 'torridon',
                    'glencoe', 'nevis', 'cairngorm', 'edinburgh', 'glasgow', 'inverness'
                ]
                
                for page in web_response.web_detection.pages_with_matching_images:
                    if page.page_title:
                        for keyword in scotland_keywords:
                            if keyword in page.page_title.lower():
                                all_tags.add(keyword)
                                # Try to extract meaningful phrases around keyword
                                title_lower = page.page_title.lower()
                                index = title_lower.find(keyword)
                                if index >= 0:
                                    start = max(0, index - 15)
                                    end = min(len(title_lower), index + len(keyword) + 15)
                                    context = title_lower[start:end]
                                    # Extract words
                                    words = re.findall(r'\b[a-zA-Z]{3,}\b', context)
                                    if len(words) >= 2:
                                        if keyword in words:
                                            words.remove(keyword)
                                        for word in words[:3]:  # Limit to 3 words
                                            if word not in ['and', 'the', 'with', 'from', 'this', 'that']:
                                                all_tags.add(word)
                                                all_tags.add(f"{keyword} {word}")
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
                    
                    # Add some generic categories based on labels
                    if label_lower in ['mountain', 'hill', 'valley', 'landscape']:
                        all_tags.add('landscape')
                        all_tags.add('nature')
                        all_tags.add('outdoors')
                    
                    if label_lower in ['tree', 'forest', 'woodland']:
                        all_tags.add('forest')
                        all_tags.add('trees')
                        all_tags.add('nature')
                    
                    if label_lower in ['sea', 'ocean', 'coast', 'beach', 'shore']:
                        all_tags.add('coastal')
                        all_tags.add('seascape')
                    
                    if label_lower in ['snow', 'winter', 'ice']:
                        all_tags.add('winter')
                        all_tags.add('snow')
                    
                    if label_lower in ['hiking', 'trekking', 'walking', 'trail']:
                        all_tags.add('hiking')
                        all_tags.add('trekking')
                        all_tags.add('outdoor activity')
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
                    if len(face_response.face_annotations) > 3:
                        all_tags.add('group')
                
                # Add activity context if applicable
                if any(tag in all_tags for tag in ['kayak', 'boat', 'canoe']):
                    all_tags.add('kayaking')
                    all_tags.add('water activity')
                
                if any(tag in all_tags for tag in ['mountain', 'hill', 'hiking', 'trail']):
                    all_tags.add('hiking')
                    all_tags.add('trekking')
                    
            # If we still don't have enough tags, try object detection
            if len(all_tags) < 5:
                logger.debug("Trying object detection as fallback...")
                try:
                    object_response = vision_client.object_localization(image=vision_image)
                    for obj in object_response.localized_object_annotations:
                        if obj.score >= 0.3:
                            all_tags.add(obj.name.lower())
                            if obj.name.lower() == 'person':
                                all_tags.add('people')
                except Exception as obj_error:
                    logger.error(f"Error in object detection: {str(obj_error)}")
        except Exception as e:
            logger.error(f"Error in face detection: {str(e)}")
        
        # Add default tags if still empty
        if len(all_tags) <= 1:  # Only AutoTagged or empty
            logger.debug("Adding default tags for Scotland/wilderness...")
            all_tags.update([
                'scotland', 'wilderness', 'nature', 'outdoors', 
                'landscape', 'travel', 'adventure'
            ])
        
        # Add wilderness scotland specific tags
        if 'scotland' in all_tags:
            all_tags.add('wilderness scotland')
            all_tags.add('scottish highlands')
        
        # Add AutoTagged marker
        all_tags.add('AutoTagged')
        
        logger.debug(f"Vision analysis complete. Found {len(all_tags)} tags.")
        return list(all_tags), confidence_scores
        
    except Exception as e:
        logger.error(f"Error in Vision API detection: {str(e)}")
        logger.error(traceback.format_exc())
        return ['AutoTagged'], {}

def process_images_batch(smugmug, vision_client, album_key, images, 
                       start_index, max_count, threshold=20, process_state=None):
    """
    Process a batch of images with robust error handling and resumability
    
    Args:
        smugmug: OAuth1Session for SmugMug
        vision_client: Vision API client
        album_key: SmugMug album key
        images: List of image objects from SmugMug
        start_index: Starting index in the images list
        max_count: Maximum number of images to process
        threshold: Vision API threshold
        process_state: Optional state for resumption
        
    Returns:
        Tuple of (processed_images, failed_images, processed_indices, next_index)
    """
    processed_images = []
    failed_images = []
    processed_indices = set()
    
    # Use existing state if provided
    if process_state:
        processed_images = process_state.get('processed_images', [])
        failed_images = process_state.get('failed_images', [])
        processed_indices = process_state.get('processed_indices', [])
    
    # Calculate upper bound based on available images
    end_index = min(start_index + max_count, len(images))
    
    # Debug
    logger.debug(f"Processing batch from {start_index} to {end_index-1} (total: {len(images)} images)")
    
    # Process one image at a time for stability
    for i in range(start_index, end_index):
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
        # Skip already processed
            if i in processed_indices:
            logger.debug(f"Skipping already processed image at index {i}")
            continue
            
        image = images[i]
        try:
            # Check if already tagged
            current_keywords = image.get('KeywordArray', [])
            if current_keywords and 'AutoTagged' in current_keywords:
                logger.debug(f"Image {image.get('FileName', 'Unknown')} already tagged, skipping")
                processed_indices.add(i)
                # Force garbage collection after each image to manage memory
            if i % 2 == 0:  # Run GC every 2 images
                import gc
                gc.collect()
                continue
            
            # Get image URLs
            image_key = f"{image['ImageKey']}-0"
            image_url = image.get('ArchivedUri') or image.get('WebUri')
            thumbnail_url = image.get('ThumbnailUrl')
            
            if not image_url:
                logger.debug(f"No image URL found for {image.get('FileName', 'Unknown')}, skipping")
                failed_images.append(image.get('FileName', 'Unknown'))
                continue
            
            # Get Vision AI tags
            logger.debug(f"Getting Vision AI tags for {image.get('FileName', 'Unknown')}")
            vision_tags, confidence_scores = get_vision_tags(vision_client, image_url, threshold)
            
            if not vision_tags or len(vision_tags) <= 1:  # Only "AutoTagged" tag
                logger.debug(f"No useful tags returned from Vision API for {image.get('FileName', 'Unknown')}, trying again with default tags")
                vision_tags = ['scotland', 'wilderness', 'outdoors', 'nature', 'landscape', 'AutoTagged']
            
            # Ensure current_keywords is a list
            if current_keywords is None:
                current_keywords = []
            elif isinstance(current_keywords, str):
                current_keywords = [current_keywords]
            
            # Filter out empty tags
            vision_tags = [tag for tag in vision_tags if tag.strip()]
            
            # Combine with existing tags
            all_tags = list(dict.fromkeys(current_keywords + vision_tags))
            logger.debug(f"Combined {len(all_tags)} tags for {image.get('FileName', 'Unknown')}")
            
            # Update the image
            logger.debug(f"Updating image {image_key}")
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
                logger.debug(f"Error updating base image: {base_response.status_code}")
                error_text = base_response.text
                if len(error_text) > 500:
                    error_text = error_text[:500] + "..."
                logger.debug(f"Response: {error_text}")
                failed_images.append(image.get('FileName', 'Unknown'))
                continue
            
            # Success
            logger.debug(f"Successfully tagged image {image.get('FileName', 'Unknown')}")
            processed_images.append({
                'filename': image.get('FileName', 'Unknown'),
                'keywords': all_tags,
                'thumbnailUrl': thumbnail_url
            })
            processed_indices.add(i)
            
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.debug(f"Error processing image: {str(e)}")
            logger.debug(f"Error trace: {error_trace}")
            failed_images.append(image.get('FileName', 'Unknown'))
        
        # Pause between images - important for stability
        time.sleep(3)
    
    # Set next index - end of current batch, or -1 if we've finished all images
    next_index = end_index if end_index < len(images) else -1
    
    return processed_images, failed_images, processed_indices, next_index

def process_album_background(session_id, start_index, batch_size=2):
    """Background thread function to process an entire album automatically"""
    try:
        # Load session state
        state = load_progress(session_id)
        if not state:
            logger.error(f"No session state found for {session_id}")
            return
        
        # Mark session as processing
        save_progress(
            session_id, 
            state['album_key'], 
            state['album_name'], 
            state['album_url'], 
            state['total_images'], 
            state['processed_indices'], 
            state['processed_images'], 
            state['failed_images'], 
            state['next_index'],
            is_processing=True
        )
        
        logger.debug(f"Starting background processing for session {session_id} from index {start_index}")
        
        # Setup SmugMug client
        tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
        api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
        api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
        
        smugmug = OAuth1Session(
            api_key,
            client_secret=api_secret,
            resource_owner_key=tokens['access_token'],
            resource_owner_secret=tokens['access_token_secret']
        )
        
        # Setup Google Cloud Vision client
        credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        
        # Create a persistent file for the entire process
        temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
        temp_file.write(credentials_json)
        temp_file.close()
        temp_file_path = temp_file.name
        
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_file_path
        vision_client = vision.ImageAnnotatorClient()
        
        # Get album images
        response = smugmug.get(
            f'https://api.smugmug.com/api/v2/album/{state["album_key"]}!images',
            params={
                '_filter': 'ImageKey,FileName,ThumbnailUrl,ArchivedUri,WebUri,KeywordArray'
            },
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get images: {response.status_code}")
            logger.error(response.text)
            return
        
        images = response.json()['Response'].get('AlbumImage', [])
        total_images = len(images)
        
        current_index = start_index
        threshold = 30  # Default threshold
        
        # Process all remaining batches
        while current_index < total_images:
            # Reload state to get any updates
            current_state = load_progress(session_id)
            
            # Process next batch
            new_processed, new_failed, updated_indices, next_index = process_images_batch(
                smugmug, vision_client, state['album_key'], images, 
                current_index, batch_size, threshold, current_state
            )
            
            # Update processed images and indices
            processed_images = current_state['processed_images']
            processed_images.extend(new_processed)
            
            failed_images = current_state['failed_images']
            failed_images.extend(new_failed)
            
            processed_indices = current_state['processed_indices']
            processed_indices.update(updated_indices)
            
            # Save updated progress
            save_progress(
                session_id, 
                state['album_key'], 
                state['album_name'], 
                state['album_url'], 
                total_images, 
                processed_indices, 
                processed_images, 
                failed_images, 
                next_index,
                is_processing=(next_index != -1)
            )
            
            # Update current index for next batch
            if next_index == -1:
                # All done
                logger.debug(f"Completed processing all images for session {session_id}")
                break
                
            current_index = next_index
            
        # Clean up temp file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            
        # Remove from background tasks
        if session_id in BACKGROUND_TASKS:
            del BACKGROUND_TASKS[session_id]
            
    except Exception as e:
        logger.error(f"Error in background processing: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Mark session as not processing
        state = load_progress(session_id)
        if state:
            save_progress(
                session_id, 
                state['album_key'], 
                state['album_name'], 
                state['album_url'], 
                state['total_images'], 
                state['processed_indices'], 
                state['processed_images'], 
                state['failed_images'], 
                state['next_index'],
                is_processing=False
            )
        
        # Remove from background tasks
        if session_id in BACKGROUND_TASKS:
            del BACKGROUND_TASKS[session_id]

@app.route('/')
def index():
    """Render the main page with improved UI"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """Process the album URL and threshold from the form with robust resumability"""
    debug_info = []
    temp_file_path = None
    
    try:
        # Get parameters from form
        url = request.form.get('album_url')
        threshold = float(request.form.get('threshold', 20))
        start_index = int(request.form.get('start_index', 0))
        session_id = request.form.get('session_id')
        
        debug_info.append(f"Processing URL: {url}")
        debug_info.append(f"Threshold: {threshold}")
        debug_info.append(f"Start index: {start_index}")
        debug_info.append(f"Session ID: {session_id}")
        
        if not url:
            return jsonify({"error": "No URL provided", "debug": debug_info})
        
        # Generate session ID if not provided
        if not session_id:
            session_id = generate_session_id(url, threshold)
            debug_info.append(f"Generated session ID: {session_id}")
        
        # Check for existing state
        existing_state = load_progress(session_id)
        if existing_state and start_index == 0:
            # We have existing state but user is starting from beginning
            # Use the existing state's next_index to continue where we left off
            start_index = existing_state.get('next_index', 0)
            if start_index == -1:  # All images were processed
                start_index = 0  # Start over
            debug_info.append(f"Resuming from index: {start_index}")
        
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
            auth_nickname = user_data['NickName']
            debug_info.append(f"Authenticated as: {auth_nickname}")
            
# If we have existing state, we can skip the album lookup
            album_key = None
            album_url = None
            album_name = None  # Initialize to None at this point
            images = None
            
            if existing_state:
                album_key = existing_state.get('album_key')
                album_url = existing_state.get('album_url')
                album_name = existing_state.get('album_name')
                debug_info.append(f"Using cached album info: {album_name} ({album_key})")
                
                # We still need to fetch images from the API
                # Can't cache them due to potential memory issues
            
            # If no cached album info, look it up
            if not album_key:
                # Extract album path and username from URL
                username, album_path = extract_album_info_from_url(url)
                
                if not username or not album_path:
                    debug_info.append("Failed to parse URL - Using fallback method")
                    album_path = get_path_from_url(url)
                    username = auth_nickname  # Fall back to authenticated user
                
                debug_info.append(f"Album owner: {username}")
                debug_info.append(f"Album path: {album_path}")
                
                # Get album info
                debug_info.append(f"Looking up album...")
                response = smugmug.get(
                    f'https://api.smugmug.com/api/v2/user/{username}!urlpathlookup',
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
                album_url = album_data['WebUri']
                debug_info.append(f"Found album: '{album_name}' with key: {album_key}")
            
            # If we get here, ensure album_name is set to something in case of an error
            if album_name is None:
                album_name = "Unknown Album"
                
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
            total_images = len(images)
            debug_info.append(f"Found {total_images} images in the album")
            
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
                    "albumUrl": album_url,
                    "debug": debug_info
                })
            
            # Process images in a small batch to avoid timeouts
            # We will process max 2 images per batch
            max_images_per_batch = 2
            debug_info.append(f"Processing up to {max_images_per_batch} images per batch")
            
            # Initialize from existing state if available
            processed_images = []
            failed_images = []
            processed_indices = set()
            
            if existing_state:
                processed_images = existing_state.get('processed_images', [])
                failed_images = existing_state.get('failed_images', [])
                processed_indices = existing_state.get('processed_indices', [])
                debug_info.append(f"Loaded {len(processed_images)} previously processed images from session")
            
            # Process batch
            new_processed, new_failed, updated_indices, next_index = process_images_batch(
                smugmug, vision_client, album_key, images, 
                start_index, max_images_per_batch, threshold,
                existing_state
            )
            
            # Combine results
            processed_images.extend(new_processed)
            failed_images.extend(new_failed)
            processed_indices.update(updated_indices)
            
            # Save progress
            state = save_progress(
                session_id, album_key, album_name, album_url, 
                total_images, processed_indices, processed_images, 
                failed_images, next_index
            )
            
            # Start background processing for remaining images
            if next_index != -1 and session_id not in BACKGROUND_TASKS:
                debug_info.append("Starting background processing for remaining images")
                
                # Launch background thread
                background_thread = threading.Thread(
                    target=process_album_background,
                    args=(session_id, next_index, 2)  # Process 2 images per batch
                )
                background_thread.daemon = True  # Allow thread to exit when main thread exits
                background_thread.start()
                
                # Store thread reference
                BACKGROUND_TASKS[session_id] = background_thread
            
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    debug_info.append("Cleaned up temporary credentials file")
                except Exception as e:
                    debug_info.append(f"Error removing temp file: {str(e)}")
            
            # Calculate progress information
            remaining_images = total_images - len(processed_indices)
            
            # Create message
            if next_index == -1:
                # All images processed
                message = f"Processing complete! {len(processed_images)} images tagged successfully, {len(failed_images)} failed."
            else:
                # More images to process
                message = f"Processed {len(processed_indices)} of {total_images} images so far ({len(processed_indices) / total_images * 100:.1f}%). "
                message += f"The remaining images are being processed automatically in the background."
            
            return jsonify({
                "success": True,
                "message": message,
                "processedImages": new_processed,  # Only return newly processed images
                "failedImages": new_failed,  # Only return newly failed images
                "totalImages": total_images,
                "processedCount": len(processed_indices),
                "failedCount": len(failed_images),
                "remainingCount": remaining_images,
                "nextIndex": next_index,
                "sessionId": session_id,
                "albumUrl": album_url,
                "albumName": album_name,
                "isComplete": next_index == -1,
                "isProcessing": session_id in BACKGROUND_TASKS,
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

@app.route('/sessions', methods=['GET'])
def list_sessions():
    """List active processing sessions"""
    sessions = []
    
    for session_id, data in PROCESS_STATE.items():
        sessions.append({
            'id': session_id,
            'albumName': data.get('album_name', 'Unknown Album'),
            'totalImages': data.get('total_images', 0),
            'processed': len(data.get('processed_indices', [])),
            'lastUpdated': data.get('last_updated', ''),
            'nextIndex': data.get('next_index', -1),
            'isComplete': data.get('next_index', -1) == -1,
            'isProcessing': session_id in BACKGROUND_TASKS  # Check if a thread is processing this session
        })
    
    # Sort by last updated, newest first
    sessions.sort(key=lambda x: x.get('lastUpdated', ''), reverse=True)
    
    return jsonify(sessions)

@app.route('/session/<session_id>', methods=['GET'])
def get_session(session_id):
    """Get details for a specific session"""
    session_data = load_progress(session_id)
    
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
        
    return jsonify({
        'id': session_id,
        'albumName': session_data.get('album_name', 'Unknown Album'),
        'albumUrl': session_data.get('album_url', ''),
        'totalImages': session_data.get('total_images', 0),
        'processed': len(session_data.get('processed_indices', [])),
        'processedImages': session_data.get('processed_images', []),
        'failedImages': session_data.get('failed_images', []),
        'lastUpdated': session_data.get('last_updated', ''),
        'nextIndex': session_data.get('next_index', -1),
        'isComplete': session_data.get('next_index', -1) == -1,
        'isProcessing': session_id in BACKGROUND_TASKS  # Check if a thread is processing this session
    })

@app.route('/clear-session/<session_id>', methods=['POST'])
def clear_session(session_id):
    """Clear a specific session"""
    if session_id in PROCESS_STATE:
        # Stop background processing if active
        if session_id in BACKGROUND_TASKS:
            # Note: We can't really "stop" a thread, but we'll remove the reference
            # The thread will continue running but will eventually exit naturally
            del BACKGROUND_TASKS[session_id]
            
        del PROCESS_STATE[session_id]
        return jsonify({"success": True, "message": "Session cleared"})
    
    return jsonify({"error": "Session not found"}), 404

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

@app.route('/status')
def status():
    """Show processing status for all sessions"""
    return jsonify({
        "active_sessions": len(PROCESS_STATE),
        "background_tasks": len(BACKGROUND_TASKS),
        "sessions": [
            {
                "id": session_id,
                "album": data.get("album_name", "Unknown"),
                "total": data.get("total_images", 0),
                "processed": len(data.get("processed_indices", [])),
                "status": "processing" if session_id in BACKGROUND_TASKS else 
                         "complete" if data.get("next_index", -1) == -1 else "paused"
            }
            for session_id, data in PROCESS_STATE.items()
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
