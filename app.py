from flask import Flask, request, jsonify, render_template
import json
import os
import logging
import traceback
from pathlib import Path

# Import the main processing function
from smugmug_web_env import test_album_tag_writing

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more details
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """Process the album URL and threshold from the form"""
    try:
        url = request.form.get('album_url')
        threshold = float(request.form.get('threshold', 30))
        
        if not url:
            logger.error("No URL provided")
            return jsonify({"error": "No URL provided"})
        
        logger.info(f"Processing album URL: {url}")
        
        # Add more detailed logging
        logger.debug("Checking environment variables...")
        has_smugmug_tokens = bool(os.environ.get('SMUGMUG_TOKENS'))
        has_google_creds = bool(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        logger.debug(f"Environment check - SMUGMUG_TOKENS: {has_smugmug_tokens}, GOOGLE_CREDENTIALS: {has_google_creds}")
        
        # Process the album
        result = test_album_tag_writing(url, threshold)
        
        # Parse JSON result to dict
        result_dict = json.loads(result)
        logger.info(f"Processing result: {result_dict}")
        return jsonify(result_dict)
    
    except Exception as e:
        # Get detailed traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error processing request: {str(e)}")
        logger.error(f"Traceback: {error_traceback}")
        return jsonify({"error": str(e), "traceback": error_traceback})

@app.route('/test-credentials')
def test_credentials():
    """Test if credentials are working properly"""
    try:
        # Test SmugMug credentials
        smugmug_test = "Not configured"
        google_test = "Not configured"
        
        if os.environ.get('SMUGMUG_TOKENS'):
            try:
                import json
                from requests_oauthlib import OAuth1Session
                
                tokens = json.loads(os.environ.get('SMUGMUG_TOKENS'))
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
                    smugmug_test = f"Working - Connected as: {user_data.get('NickName', 'Unknown')}"
                else:
                    smugmug_test = f"Failed - Status code: {response.status_code}"
            except Exception as e:
                smugmug_test = f"Error: {str(e)}"
        
        # Test Google credentials
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
            try:
                import tempfile
                from google.cloud import vision
                
                with tempfile.NamedTemporaryFile(delete=False, mode='w') as temp:
                    temp.write(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
                    temp_path = temp.name
                
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_path
                
                # Try to initialize the client
                vision_client = vision.ImageAnnotatorClient()
                google_test = "Working - Successfully initialized Vision client"
                
                # Clean up temp file
                os.unlink(temp_path)
            except Exception as e:
                google_test = f"Error: {str(e)}"
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
        
        return jsonify({
            "smugmug_credentials": smugmug_test,
            "google_credentials": google_test
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
# Replacing import statement at the top of the file
# Replace: from smugmug_web_env import test_album_tag_writing
# With: from smugmug_web_env_debug import test_album_tag_writing
@app.route('/diagnostic')
def diagnostic():
    """Diagnostic page for troubleshooting"""
    return render_template('diagnostic.html')
