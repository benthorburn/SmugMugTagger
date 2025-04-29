from google.cloud import vision
import os
from pathlib import Path

def test_vision_api():
    print("\nGoogle Vision API Test")
    print("====================\n")
    
    # Set up credentials
    creds_path = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_path)
    
    # Image URL from SmugMug
    image_url = "https://photos.smugmug.com/photos/i-RkDfpk8/0/MJB6HGcVqqCGwGv4VwdZZLPSbPPPHjzq8MFTm938L/O/i-RkDfpk8-O.jpg"
    
    print(f"Testing with image URL: {image_url}")
    
    try:
        # Create client
        client = vision.ImageAnnotatorClient()
        
        # Create image object
        image = vision.Image()
        image.source.image_uri = image_url
        
        # Get features we want to detect
        features = [
            vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION),
            vision.Feature(type_=vision.Feature.Type.LANDMARK_DETECTION),
            vision.Feature(type_=vision.Feature.Type.WEB_DETECTION)
        ]
        
        # Make request
        request = vision.AnnotateImageRequest(
            image=image,
            features=features
        )
        
        print("\nSending request to Google Vision API...")
        response = client.annotate_image(request)
        
        # Print labels
        print("\nLabels detected:")
        print("---------------")
        for label in response.label_annotations:
            confidence = label.score * 100
            print(f"- {label.description:<30} ({confidence:.1f}% confidence)")
        
        # Print landmarks
        if response.landmark_annotations:
            print("\nLandmarks detected:")
            print("------------------")
            for landmark in response.landmark_annotations:
                confidence = landmark.score * 100
                print(f"- {landmark.description:<30} ({confidence:.1f}% confidence)")
        
        # Print web entities
        if response.web_detection.web_entities:
            print("\nWeb entities detected:")
            print("--------------------")
            for entity in response.web_detection.web_entities:
                if entity.score:
                    confidence = entity.score * 100
                    print(f"- {entity.description:<30} ({confidence:.1f}% confidence)")
        
        return True
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_vision_api()
    if not success:
        print("\nVision API test failed")
    print("\nPress Enter to exit...")
    input()