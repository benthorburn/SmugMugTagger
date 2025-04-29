# SmugMug Auto Tagger

This application automatically tags images in a SmugMug album using Google Cloud Vision AI. It detects objects, scenes, landmarks, text, and other elements in your photos and applies them as keywords to your SmugMug images.

## Features

- Automatic image analysis using Google Cloud Vision AI
- Detection of objects, scenes, landmarks, text, and faces
- Web-based interface for easy album processing
- Works with existing SmugMug albums
- Preserves existing image tags

## Requirements

- SmugMug account with API access
- Google Cloud Vision API credentials
- Python 3.7 or higher

## Local Development

1. Make sure you have the required credentials in the `config` and `credentials` folders
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python app.py`
4. Visit `http://localhost:5000` in your browser

## Deployment

This application can be deployed to Render.com for cloud hosting.
