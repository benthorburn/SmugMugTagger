from requests_oauthlib import OAuth1Session
import json
from pathlib import Path
import time
from google.cloud import vision
import os
from urllib.parse import urlparse
import sys
import logging
import traceback
import tempfile

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_path_from_url(url):
    """Extract path from SmugMug URL"""
    logger.debug(f"Extracting path from URL: {url}")
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith('/app/organize'):
        path = path.replace('/app/organize', '', 1)
    final_path = path.rstrip('/')
    logger.debug(f"Extracted path: {final_path}")
    return final_path

def get_vision_tags(vision_client, image_url):
    """Get comprehensive tags using multiple Vision API features"""
    logger.info(f"Starting Vision AI analysis for: {image_url}")
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    all_tags = set()
    confidence_scores = {}
    
    try:
        # 1. Label Detection (general objects, scenes, activities)
        logger.debug("Starting label detection...")
        label_response = vision_client.label_detection(image=vision_image)
        for label in label_response.label_annotations:
            if label.score * 100 >= 30:
                label_lower = label.description.lower()
                all_tags.add(label_lower)
                confidence_scores[label_lower] = f"{label.score * 100:.1f}%"
        logger.debug(f"Label detection found {len(label_response.label_annotations)} labels")
        
        # Additional processing for other Vision features would continue here...
        logger.debug(f"Completed Vision AI analysis with {len(all_tags)} total tags")
        return list(all_tags), confidence_scores
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error in Vision API detection: {str(e)}")
        logger.error(f"Traceback: {error_details}")
        return [], {}

def test_album_tag_writing(url, threshold=30):
    try:
        logger.info(f"Starting album tag writing for URL: {url}")
        # Load SmugMug credentials - first try environment variables
        if os.environ.get('SMUGMUG_TOKENS'):
            logger.debug("Loading SmugMug tokens from environment variables")
            tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
            logger.debug("Successfully loaded SmugMug tokens from environment variables")
        else:
            # Fallback to file for local development
            logger.debug("Loading SmugMug tokens from file")
            config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
            with open(config_file) as f:
                tokens = json.load(f)
            logger.debug("Successfully loaded SmugMug tokens from file")
        
        # Setup SmugMug client
        logger.debug("Setting up SmugMug client")
        api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
        api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
        
        smugmug = OAuth1Session(
            api_key,
            client_secret=api_secret,
            resource_owner_key=tokens['access_token'],
            resource_owner_secret=tokens['access_token_secret']
        )
        logger.debug("SmugMug client initialized")

        # Setup Google Cloud Vision client
        logger.debug("Setting up Google Cloud Vision client")
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
            # Use environment variable for credentials
            logger.debug("Using Google Vision credentials from environment variables")
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
            temp
cat > smugmug_web_env_debug.py << 'EOF'
from requests_oauthlib import OAuth1Session
import json
from pathlib import Path
import time
from google.cloud import vision
import os
from urllib.parse import urlparse
import sys
import logging
import traceback
import tempfile

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_path_from_url(url):
    """Extract path from SmugMug URL"""
    logger.debug(f"Extracting path from URL: {url}")
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith('/app/organize'):
        path = path.replace('/app/organize', '', 1)
    final_path = path.rstrip('/')
    logger.debug(f"Extracted path: {final_path}")
    return final_path

def get_vision_tags(vision_client, image_url):
    """Get comprehensive tags using multiple Vision API features"""
    logger.info(f"Starting Vision AI analysis for: {image_url}")
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    all_tags = set()
    confidence_scores = {}
    
    try:
        # 1. Label Detection (general objects, scenes, activities)
        logger.debug("Starting label detection...")
        label_response = vision_client.label_detection(image=vision_image)
        for label in label_response.label_annotations:
            if label.score * 100 >= 30:
                label_lower = label.description.lower()
                all_tags.add(label_lower)
                confidence_scores[label_lower] = f"{label.score * 100:.1f}%"
        logger.debug(f"Label detection found {len(label_response.label_annotations)} labels")
        
        # Additional processing for other Vision features would continue here...
        logger.debug(f"Completed Vision AI analysis with {len(all_tags)} total tags")
        return list(all_tags), confidence_scores
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error in Vision API detection: {str(e)}")
        logger.error(f"Traceback: {error_details}")
        return [], {}

def test_album_tag_writing(url, threshold=30):
    try:
        logger.info(f"Starting album tag writing for URL: {url}")
        # Load SmugMug credentials - first try environment variables
        if os.environ.get('SMUGMUG_TOKENS'):
            logger.debug("Loading SmugMug tokens from environment variables")
            tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
            logger.debug("Successfully loaded SmugMug tokens from environment variables")
        else:
            # Fallback to file for local development
            logger.debug("Loading SmugMug tokens from file")
            config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
            with open(config_file) as f:
                tokens = json.load(f)
            logger.debug("Successfully loaded SmugMug tokens from file")
        
        # Setup SmugMug client
        logger.debug("Setting up SmugMug client")
        api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
        api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
        
        smugmug = OAuth1Session(
            api_key,
            client_secret=api_secret,
            resource_owner_key=tokens['access_token'],
            resource_owner_secret=tokens['access_token_secret']
        )
        logger.debug("SmugMug client initialized")

        # Setup Google Cloud Vision client
        logger.debug("Setting up Google Cloud Vision client")
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
            # Use environment variable for credentials
            logger.debug("Using Google Vision credentials from environment variables")
            credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
            temp_file.write(credentials_json)
            temp_file.close()
            credentials_path = temp_file.name
            logger.debug(f"Created temporary credentials file at: {credentials_path}")
            
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            logger.debug("Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
            
            try:
                vision_client = vision.ImageAnnotatorClient()
                logger.debug("Successfully initialized Vision client")
            except Exception as e:
                logger.error(f"Error initializing Vision client: {str(e)}")
                os.unlink(credentials_path)
                raise
        else:
            # Fallback to file for local development
            logger.debug("Using Google Vision credentials from file")
            creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
            vision_client = vision.ImageAnnotatorClient()
            logger.debug("Successfully initialized Vision client from file")
        
        album_path = get_path_from_url(url)
        logger.info(f"Processing album path: {album_path}")
        
        # Get user info
        logger.debug("Getting user info from SmugMug API")
        response = smugmug.get(
            'https://api.smugmug.com/api/v2!authuser',
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            error_msg = f"Failed to get user info: Status code {response.status_code}"
            logger.error(error_msg)
            logger.error(f"Response: {response.text}")
            return json.dumps({"error": error_msg})
            
        user_data = response.json()['Response']['User']
        nickname = user_data['NickName']
        logger.debug(f"Successfully got user info for: {nickname}")
        
        # Get album info
        logger.debug(f"Looking up album with path: {album_path}")
        response = smugmug.get(
            f'https://api.smugmug.com/api/v2/user/{nickname}!urlpathlookup',
            params={'urlpath': album_path},
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            error_msg = f"Failed to find album: Status code {response.status_code}"
            logger.error(error_msg)
            logger.error(f"Response: {response.text}")
            return json.dumps({"error": error_msg})
        
        # Check if we have an Album in the response
        response_data = response.json()['Response']
        if 'Album' not in response_data:
            available_keys = ', '.join(response_data.keys())
            error_msg = f"Album not found in response. Available keys: {available_keys}"
            logger.error(error_msg)
            logger.error(f"Response: {json.dumps(response_data)}")
            return json.dumps({"error": error_msg})
            
        album_data = response_data['Album']
        album_key = album_data['AlbumKey']
        logger.debug(f"Found album: {album_data['Name']} with key: {album_key}")
        
        # Get images with expanded details
        logger.debug(f"Getting images for album key: {album_key}")
        response = smugmug.get(
            f'https://api.smugmug.com/api/v2/album/{album_key}!images',
            params={
                '_expand': 'ImageSizes,ImageMetadata',
                '_shorturis': 1,
                '_filter': 'ImageKey,FileName,ThumbnailUrl,ArchivedUri,WebUri,KeywordArray'
            },
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            error_msg = f"Failed to get album images: Status code {response.status_code}"
            logger.error(error_msg)
            logger.error(f"Response: {response.text}")
            return json.dumps({"error": error_msg})
        
        response_json = response.json()
        if 'Response' not in response_json:
            error_msg = "No Response key in API result"
            logger.error(error_msg)
            logger.error(f"Response: {json.dumps(response_json)}")
            return json.dumps({"error": error_msg})
            
        images = response_json['Response'].get('AlbumImage', [])
        logger.info(f"Found {len(images)} images in album")
        
        # Clean up temp file if it exists
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON') and 'credentials_path' in locals():
            try:
                os.unlink(credentials_path)
                logger.debug("Cleaned up temporary credentials file")
            except Exception as e:
                logger.warning(f"Error removing temp credentials file: {str(e)}")
        
        if not images:
            return json.dumps({
                "success": True,
                "processedImages": [],
                "failedImages": [],
                "totalImages": 0,
                "successfullyProcessed": 0,
                "failed": 0,
                "albumUrl": album_data['WebUri'],
                "message": "No images found in the album"
            })
        
        # Processing images would continue here...
        # For now, let's return a test result
        return json.dumps({
            "success": True,
            "processedImages": [],
            "failedImages": [],
            "totalImages": len(images),
            "successfullyProcessed": 0,
            "failed": 0,
            "albumUrl": album_data['WebUri'],
            "message": "Found album and images - debugging in progress"
        })

    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error in main process: {str(e)}")
        logger.error(f"Traceback: {error_details}")
        return json.dumps({"error": str(e), "traceback": error_details})
