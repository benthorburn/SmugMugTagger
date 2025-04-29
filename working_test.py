from google.cloud import vision
import json
import os
from requests_oauthlib import OAuth1Session
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
import requests
from io import BytesIO
from urllib.parse import urlparse

def get_image_exif(image_url):
    """Extract EXIF data from image"""
    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        
        exif_data = {}
        if hasattr(img, '_getexif'):
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif_data[tag] = value
                    
        return exif_data
    except Exception as e:
        print(f"Error getting EXIF data: {str(e)}")
        return {}

def get_vision_tags(vision_client, image_url):
    """Get comprehensive tags using multiple detection features"""
    vision_image = vision.Image()
    vision_image.source.image_uri = image_url
    
    all_tags = set()
    confidence_scores = {}
    
    try:
        # Get EXIF data
        exif_data = get_image_exif(image_url)
        
        # Extract GPS coordinates if available
        lat = None
        lon = None
        if 'GPSInfo' in exif_data:
            gps = exif_data['GPSInfo']
            if all(i in gps for i in (1, 2, 3, 4)):
                lat = gps[2][0] + gps[2][1]/60 + gps[2][2]/3600
                lon = gps[4][0] + gps[4][1]/60 + gps[4][2]/3600
                if gps[1] == 'S': lat = -lat
                if gps[3] == 'W': lon = -lon
        
        # Add location context to Vision request
        if lat and lon:
            location_context = vision.LocationContext(
                lat_lng={'latitude': lat, 'longitude': lon}
            )
            vision_image.context = vision.ImageContext(
                location_info=location_context
            )
        
        # Enhanced detection features
        
        # Labels (general objects, activities)
        label_response = vision_client.label_detection(image=vision_image)
        for label in label_response.label_annotations:
            if label.score * 100 >= 30:
                all_tags.add(label.description)
                confidence_scores[label.description] = f"{label.score * 100:.1f}%"
        
        # Landmarks with location context
        landmark_response = vision_client.landmark_detection(image=vision_image)
        for landmark in landmark_response.landmark_annotations:
            if landmark.score * 100 >= 30:
                all_tags.add(landmark.description)
                # Add location hierarchy
                if landmark.locations:
                    for location in landmark.locations:
                        if location.lat_lng:
                            from geopy.geocoders import Nominatim
                            geolocator = Nominatim(user_agent="smugmug_tagger")
                            location = geolocator.reverse(f"{location.lat_lng.latitude}, {location.lat_lng.longitude}")
                            if location:
                                address = location.raw['address']
                                # Add region-specific tags
                                if 'country' in address:
                                    all_tags.add(address['country'])
                                if 'region' in address:
                                    all_tags.add(address['region'])
                                if 'county' in address:
                                    all_tags.add(address['county'])
        
        # Object localization
        object_response = vision_client.object_localization(image=vision_image)
        for obj in object_response.localized_object_annotations:
            if obj.score * 100 >= 30:
                all_tags.add(obj.name)
                confidence_scores[obj.name] = f"{obj.score * 100:.1f}%"
        
        # Text detection (OCR)
        text_response = vision_client.text_detection(image=vision_image)
        if text_response.text_annotations:
            # Add relevant text as tags (e.g., place names, signs)
            main_text = text_response.text_annotations[0]
            text_tags = [word for word in main_text.description.split() if len(word) > 3]
            all_tags.update(text_tags)
        
        # Logo detection
        logo_response = vision_client.logo_detection(image=vision_image)
        for logo in logo_response.logo_annotations:
            if logo.score * 100 >= 30:
                all_tags.add(f"{logo.description} logo")
        
        # Weather & season detection from properties
        property_response = vision_client.image_properties(image=vision_image)
        if property_response.image_properties_annotation:
            colors = property_response.image_properties_annotation.dominant_colors.colors
            
            # Detect weather conditions
            blue_sky = any(c.color.blue > 200 and c.color.blue > c.color.red for c in colors)
            grey_sky = any(all(160 < x < 190 for x in [c.color.red, c.color.green, c.color.blue]) for c in colors)
            if blue_sky:
                all_tags.add("clear sky")
            if grey_sky:
                all_tags.add("overcast")
                
            # Detect seasons
            green_foliage = any(c.color.green > 150 and c.color.green > c.color.red and c.color.green > c.color.blue for c in colors)
            autumn_colors = any(c.color.red > 180 and c.color.red > c.color.blue for c in colors)
            if green_foliage:
                all_tags.add("summer")
            if autumn_colors:
                all_tags.add("autumn")
        
        # Safe search annotations
        safe_response = vision_client.safe_search_detection(image=vision_image)
        if safe_response.safe_search_annotation:
            # Add activity-related tags
            if safe_response.safe_search_annotation.violence == vision.Likelihood.LIKELY:
                all_tags.add("action")
            if safe_response.safe_search_annotation.spoof == vision.Likelihood.LIKELY:
                all_tags.add("staged photo")
        
        # Add time-of-day tags if available in EXIF
        if 'DateTime' in exif_data:
            from datetime import datetime
            time = datetime.strptime(exif_data['DateTime'], '%Y:%m:%d %H:%M:%S').time()
            if 5 <= time.hour < 12:
                all_tags.add("morning")
            elif 12 <= time.hour < 17:
                all_tags.add("afternoon")
            elif 17 <= time.hour < 20:
                all_tags.add("evening")
            else:
                all_tags.add("night")
        
        return list(all_tags), confidence_scores
        
    except Exception as e:
        print(f"Error in Vision API detection: {str(e)}")
        return [], {}

if __name__ == "__main__":
    # Initialize Vision client
    try:
        credentials_path = os.path.join(os.path.expanduser('~'), 'Desktop', 'SmugMugTagger', 'credentials', 'google_credentials.json')
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        vision_client = vision.ImageAnnotatorClient()
        print("Successfully initialized Vision client")
    except Exception as e:
        print(f"Error initializing Vision client: {str(e)}")
        exit(1)

    # Initialize SmugMug client
    try:
        config_file = os.path.join(os.path.expanduser('~'), 'Desktop', 'SmugMugTagger', 'config', 'smugmug_tokens.json')
        with open(config_file) as f:
            tokens = json.load(f)
            
        api_key = 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq'
        api_secret = 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR'
        
        smugmug = OAuth1Session(
            api_key,
            client_secret=api_secret,
            resource_owner_key=tokens['access_token'],
            resource_owner_secret=tokens['access_token_secret']
        )
        print("Successfully initialized SmugMug client")
    except Exception as e:
        print(f"Error initializing SmugMug client: {str(e)}")
        exit(1)

    # Get album URL from user
    print("\nEnter SmugMug album URL:")
    album_url = input().strip()
    
    try:
        # First get the user nickname
        response = smugmug.get(
            'https://api.smugmug.com/api/v2!authuser',
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            print(f"Error accessing SmugMug: {response.status_code}")
            exit(1)
            
        user_data = response.json()
        nickname = user_data['Response']['User']['NickName']
        
        # Extract path from URL
        parsed_url = urlparse(album_url)
        path = parsed_url.path
        
        # Use URL path lookup to get album URI
        lookup_url = f'https://api.smugmug.com/api/v2/user/{nickname}!urlpathlookup'
        response = smugmug.get(
            lookup_url,
            params={'urlpath': path},
            headers={'Accept': 'application/json'}
        )
        
        if response.status_code != 200:
            print(f"Error looking up album: {response.status_code}")
            print(response.text)
            exit(1)
            
        data = response.json()
        if 'Response' not in data or 'Album' not in data['Response']:
            print("Could not find album. Please check the URL.")
            exit(1)
            
        album_uri = data['Response']['Album']['Uri']
        print(f"Found album: {album_uri}")

        # Now process the album's images
        print(f"\nFetching images from album...")
        images_response = smugmug.get(
            f'https://api.smugmug.com{album_uri}/!images',
            headers={'Accept': 'application/json'}
        )
        
        if images_response.status_code != 200:
            print(f"Error accessing album images: {images_response.status_code}")
            print(images_response.text)
            exit(1)
            
        images_data = images_response.json()
        if 'Response' not in images_data or 'AlbumImage' not in images_data['Response']:
            print("No images found in album")
            exit(1)
            
        images = images_data['Response']['AlbumImage']
        print(f"Found {len(images)} images")
        
        # Process each image
        for i, image in enumerate(images, 1):
            print(f"\nProcessing image {i}/{len(images)}: {image.get('FileName', 'Unknown')}")
            image_uri = image['Uri']
            
            # Get image details to get URL
            detail_response = smugmug.get(
                f'https://api.smugmug.com{image_uri}',
                headers={'Accept': 'application/json'}
            )
            
            if detail_response.status_code == 200:
                detail_data = detail_response.json()
                if 'Response' in detail_data and 'Image' in detail_data['Response']:
                    image_url = detail_data['Response']['Image'].get('ArchivedUri')
                    if image_url:
                        # Get tags
                        print(f"Getting AI tags for image {i}...")
                        tags, confidence_scores = get_vision_tags(vision_client, image_url)
                        
                        if tags:
                            print(f"\nFound {len(tags)} tags for image {i}:")
                            for tag in sorted(tags):
                                confidence = confidence_scores.get(tag, 'N/A')
                                print(f"- {tag} (Confidence: {confidence})")
                            
                            # Update image with new tags
                            print(f"\nUpdating image {i} with new tags...")
                            update_response = smugmug.patch(
                                f'https://api.smugmug.com{image_uri}',
                                json={'Keywords': ','.join(tags)},
                                headers={'Accept': 'application/json', 'Content-Type': 'application/json'}
                            )
                            
                            if update_response.status_code == 200:
                                print(f"✓ Successfully updated tags for image {i}")
                            else:
                                print(f"✗ Failed to update tags for image {i}: {update_response.status_code}")
                        else:
                            print(f"No tags generated for image {i}")
            
            print("-" * 80)
            
        print("\nFinished processing all images")
                
    except Exception as e:
        print(f"Error processing album: {str(e)}")
        exit(1)