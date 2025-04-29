from flask import Flask, request, jsonify, render_template
import json
import os
import logging
from pathlib import Path

# Import the main processing function
from smugmug_web_env import test_album_tag_writing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
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
            return jsonify({"error": "No URL provided"})
        
        logger.info(f"Processing album URL: {url}")
        result = test_album_tag_writing(url, threshold)
        
        # Parse JSON result to dict
        result_dict = json.loads(result)
        return jsonify(result_dict)
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
