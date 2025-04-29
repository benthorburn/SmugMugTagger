import os
from pathlib import Path
import json
from google.cloud import vision
from requests_oauthlib import OAuth1Session
import warnings
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
from datetime import datetime, timedelta

# Suppress warnings
warnings.filterwarnings("ignore")

class SmugMugTagger:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback or print
        self.setup_clients()
        
    def log(self, message):
        """Log a message through the callback"""
        self.status_callback(message)
        
    def setup_clients(self):
        """Initialize API clients"""
        config_file = Path.home() / "Desktop" / "SmugMugTagger" / "config" / "smugmug_tokens.json"
        with open(config_file) as f:
            tokens = json.load(f)
            
        # SmugMug setup
        self.api_key = 'jFhhPG4GQcm7VRRqs7m3ndXjHMxgp9Dq'
        self.api_secret = 'C2Z7nFsXBMvMpvzq5NhRp9DqsJN7kDThP744WCr34cmPk4b24NdPB3sz6gNBPzjR'
        
        self.smugmug = OAuth1Session(
            self.api_key,
            client_secret=self.api_secret,
            resource_owner_key=tokens['access_token'],
            resource_owner_secret=tokens['access_token_secret']
        )
        
        # Google Vision setup
        creds_file = Path.home() / "Desktop" / "SmugMugTagger" / "credentials" / "google_credentials.json"
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(creds_file)
        self.vision_client = vision.ImageAnnotatorClient()
        
    def get_october_images(self):
        """Get images uploaded since October 1st, 2024"""
        try:
            # Get user info
            response = self.smugmug.get(
                'https://api.smugmug.com/api/v2!authuser',
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code != 200:
                self.log(f"Error accessing SmugMug: {response.status_code}")
                return []
                
            user_data = response.json()
            nickname = user_data['Response']['User']['NickName']
            self.log(f"\nConnected as: {nickname}")
            
            # Get all images
            self.log("\nFetching images since October 1st...")
            images_url = f'https://api.smugmug.com/api/v2/user/{nickname}!images'
            
            response = self.smugmug.get(
                images_url,
                params={
                    'start': 1,
                    'count': 100,  # Adjust if needed
                    'Extras': 'FileName,Keywords,Uri,ImageKey,Title,DateUploaded,WebUrl',
                    '_filter': 'DateUploaded,ge,2024-10-01'  # Filter for October images
                },
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code != 200:
                self.log(f"Error fetching images: {response.status_code}")
                self.log(f"Response: {response.text}")
                return []
            
            data = response.json()
            if 'Response' not in data or 'Image' not in data['Response']:
                self.log("No images found in response")
                return []
            
            images = data['Response']['Image']
            self.log(f"Found {len(images)} images uploaded since October 1st")
            return images
            
        except Exception as e:
            self.log(f"Error getting images: {str(e)}")
            return []
            
    def get_image_url(self, image):
        """Get full resolution URL for an image"""
        try:
            response = self.smugmug.get(
                image['Uri'],
                params={'_config': 'CloudAPI'},
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'Response' in data and 'Image' in data['Response']:
                    img_data = data['Response']['Image']
                    if 'Uris' in img_data and 'LargestImage' in img_data['Uris']:
                        return img_data['Uris']['LargestImage']['Uri']
                        
            return image.get('WebUrl')  # Fallback to WebUrl if available
            
        except Exception as e:
            self.log(f"Error getting image URL: {str(e)}")
            return None
            
    def process_image(self, image):
        """Process a single image with Vision API"""
        try:
            self.log(f"\nProcessing: {image['FileName']}")
            
            # Get image URL
            image_url = self.get_image_url(image)
            if not image_url:
                self.log("Could not get image URL")
                return False
                
            self.log("Getting AI tags...")
            
            # Get Vision tags
            vision_image = vision.Image()
            vision_image.source.image_uri = image_url
            response = self.vision_client.label_detection(image=vision_image)
            
            # Process tags
            new_tags = [label.description.lower() for label in response.label_annotations]
            existing_tags = set(image.get('Keywords', '').split(',')) if image.get('Keywords') else set()
            existing_tags.discard('')
            
            self.log("\nExisting tags: " + (', '.join(existing_tags) if existing_tags else "None"))
            self.log("New tags: " + ', '.join(new_tags[:10]) + "...")
            
            # Combine tags
            all_tags = existing_tags.union(new_tags)
            
            # Update image metadata
            self.log("\nUpdating image metadata...")
            response = self.smugmug.patch(
                image['Uri'],
                headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
                json={'Keywords': ','.join(all_tags)}
            )
            
            if response.status_code == 200:
                self.log(f"✓ Successfully added {len(new_tags)} new tags")
                return True
            else:
                self.log(f"✗ Failed to update metadata: {response.status_code}")
                self.log(f"Response: {response.text}")
                return False
                
        except Exception as e:
            self.log(f"Error processing image: {str(e)}")
            return False
            
    def process_all_images(self):
        """Process all October images"""
        images = self.get_october_images()
        if not images:
            self.log("No images found to process")
            return
        
        total = len(images)
        processed = 0
        failed = 0
        
        for i, image in enumerate(images, 1):
            self.log(f"\n[{i}/{total}] Processing {image['FileName']}")
            upload_date = datetime.fromisoformat(image['DateUploaded'].split('T')[0])
            self.log(f"Upload date: {upload_date.strftime('%Y-%m-%d')}")
            
            if self.process_image(image):
                processed += 1
            else:
                failed += 1
                
        self.log(f"\nProcessing complete!")
        self.log(f"Successfully processed: {processed}/{total} images")
        if failed > 0:
            self.log(f"Failed to process: {failed} images")

class TaggerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SmugMug Image Tagger")
        self.root.geometry("800x800")
        self.root.configure(bg='#1f1f1f')
        
        # Set TK_SILENCE_DEPRECATION
        os.environ['TK_SILENCE_DEPRECATION'] = '1'
        
        # Configure grid
        self.root.grid_columnconfigure(0, weight=1)
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        # Title with white text
        title_label = tk.Label(
            self.root,
            text="SmugMug Automatic Image Tagging",
            font=('Georgia', 16),
            fg='white',
            bg='#1f1f1f'
        )
        title_label.grid(row=0, column=0, pady=20)
        
        # Status text
        text_frame = tk.Frame(self.root, bg='#2d2d2d', padx=2, pady=2)
        text_frame.grid(row=1, column=0, pady=20, padx=20, sticky='nsew')
        self.root.grid_rowconfigure(1, weight=1)
        
        self.status_text = tk.Text(
            text_frame,
            height=30,
            width=80,
            bg='#2d2d2d',
            fg='white',
            font=('Courier', 12)
        )
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, command=self.status_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.configure(yscrollcommand=scrollbar.set)
        
        # Buttons
        button_frame = tk.Frame(self.root, bg='#1f1f1f')
        button_frame.grid(row=2, column=0, pady=20)
        
        self.start_button = tk.Button(
            button_frame,
            text="Start Processing October Images",
            command=self.start_processing,
            font=('Georgia', 14),
            width=40,
            height=3,
            bg='#4CAF50',
            fg='white'
        )
        self.start_button.pack(side=tk.LEFT, padx=20)
        
        self.quit_button = tk.Button(
            button_frame,
            text="Quit",
            command=self.root.quit,
            font=('Georgia', 14),
            width=40,
            height=3,
            bg='#f44336',
            fg='white'
        )
        self.quit_button.pack(side=tk.LEFT, padx=20)
        
        # Initial status
        self.update_status("Ready to process October images. Click 'Start Processing' to begin.")
        
    def update_status(self, message):
        """Update status text"""
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)
        self.root.update()
        
    def start_processing(self):
        """Start processing images"""
        self.start_button.config(state='disabled')
        self.status_text.delete(1.0, tk.END)
        
        try:
            tagger = SmugMugTagger(self.update_status)
            tagger.process_all_images()
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.start_button.config(state='normal')
            
    def run(self):
        """Start the GUI"""
        self.root.mainloop()

if __name__ == "__main__":
    app = TaggerGUI()
    app.run()