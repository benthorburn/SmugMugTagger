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

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

def get_smugmug_client():
    """Initialize SmugMug client"""
    if os.environ.get('SMUGMUG_TOKENS'):
        tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
    else:
        config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
        with open(config_file) as f:
            tokens = json.load(f)
    
    api_key = os.environ.get('SMUGMUG_API_KEY', 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq')
    api_secret = os.environ.get('SMUGMUG_API_SECRET', 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR')
    
    return OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=tokens['access_token'],
        resource_owner_secret=tokens['access_token_secret']
    )

def get_vision_client():
    """Initialize Google Vision client"""
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
        credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
        temp_file.write(credentials_json)
        temp_file.close()
        credentials_path = temp_file.name
        
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        client = vision.ImageAnnotatorClient()
        
        # Clean up temp file
        os.unlink(credentials_path)
        return client
    else:
        creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
        return vision.ImageAnnotatorClient()

def get_path_from_url(url):
    """Extract path from SmugMug URL"""
    parsed = urlparse(url)
    path = parsed.path
    if path.startswith('/app/organize'):
        path = path.replace('/app/organize', '', 1)
    return path.rstrip('/')

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """Process the album URL and threshold from the form"""
    debug_info = []
    
    try:
        url = request.form.get('album_url')
        threshold = float(request.form.get('threshold', 30))
        
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
            # Step 1: Initialize SmugMug client
            debug_info.append("Initializing SmugMug client...")
            smugmug = get_smugmug_client()
            debug_info.append("SmugMug client initialized successfully")
            
            # Step 2: Get user info
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
            
            # Step 3: Extract album path
            album_path = get_path_from_url(url)
            debug_info.append(f"Extracted album path: {album_path}")
            
            # Step 4: Get album info
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
            
            # Step 5: Get images
            debug_info.append("Getting images from album...")
            response = smugmug.get(
                f'https://api.smugmug.com/api/v2/album/{album_key}!images',
                params={
                    '_expand': 'ImageSizes',
                    '_shorturis': 1,
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
                return jsonify({
                    "success": True,
                    "message": "No images found in the album",
                    "totalImages": 0,
                    "albumUrl": album_data['WebUri'],
                    "debug": debug_info
                })
            
            # For now, return success with image count
            return jsonify({
                "success": True,
                "message": f"Found {len(images)} images in album '{album_name}'",
                "totalImages": len(images),
                "albumUrl": album_data['WebUri'],
                "debug": debug_info
            })
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            debug_info.append(f"Processing error: {str(e)}")
            debug_info.append(f"Traceback: {error_traceback}")
            return jsonify({"error": str(e), "debug": debug_info})
    
    except Exception as e:
        error_traceback = traceback.format_exc()
        debug_info.append(f"Top-level error: {str(e)}")
        debug_info.append(f"Traceback: {error_traceback}")
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
                    results["vision"] = {
                        "status": "working",
                        "details": "Successfully initialized Vision client"
                    }
                except Exception as e:
                    results["vision"] = {
                        "status": "error",
                        "details": f"Error initializing Vision client: {str(e)}"
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
