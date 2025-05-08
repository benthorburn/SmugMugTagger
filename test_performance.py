#!/usr/bin/env python3
"""
Simple performance test for SmugMug Tagger application
"""
import os
import requests
import time
import json
from urllib.parse import urljoin

# Render app URL - replace with your actual URL
BASE_URL = "https://smugmugtagger.onrender.com"

# Test album URL - replace with a test album URL
TEST_ALBUM_URL = "https://YOUR_USERNAME.smugmug.com/YOUR_TEST_ALBUM"

def test_app_performance():
    """Run a simple performance test on the app"""
    print(f"Testing performance of {BASE_URL}")
    
    # Test 1: Check app responsiveness
    start_time = time.time()
    try:
        response = requests.get(BASE_URL, timeout=10)
        load_time = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ App responded in {load_time:.2f} seconds")
        else:
            print(f"❌ App returned status code {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Failed to connect to app: {str(e)}")
        return
    
    # Test 2: Check session list (should be fast)
    start_time = time.time()
    try:
        response = requests.get(urljoin(BASE_URL, "/sessions"), timeout=10)
        load_time = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Sessions endpoint responded in {load_time:.2f} seconds")
            sessions = response.json()
            print(f"   Found {len(sessions)} active sessions")
        else:
            print(f"❌ Sessions endpoint returned status code {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to connect to sessions endpoint: {str(e)}")
    
    # Test 3: Process a small batch of images (if a test album URL is provided)
    if TEST_ALBUM_URL != "https://YOUR_USERNAME.smugmug.com/YOUR_TEST_ALBUM":
        print(f"\nTesting image processing with album: {TEST_ALBUM_URL}")
        
        # Form data for processing request
        form_data = {
            "album_url": TEST_ALBUM_URL,
            "threshold": "30",
            "start_index": "0"
        }
        
        start_time = time.time()
        try:
            response = requests.post(
                urljoin(BASE_URL, "/process"),
                data=form_data,
                timeout=60  # Longer timeout for processing
            )
            process_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    print(f"❌ Processing error: {result['error']}")
                else:
                    print(f"✅ Processed {result.get('processedCount', 0)} of {result.get('totalImages', 0)} images")
                    print(f"   Processing took {process_time:.2f} seconds")
                    
                    # Check if we're using the optimized batch size
                    if "debug" in result:
                        debug_info = result["debug"]
                        batch_info = [line for line in debug_info if "batch size" in line.lower()]
                        if batch_info:
                            print(f"   {batch_info[0]}")
            else:
                print(f"❌ Processing endpoint returned status code {response.status_code}")
        except Exception as e:
            print(f"❌ Failed during processing test: {str(e)}")
    else:
        print("\nSkipping processing test - no test album URL provided")
    
    print("\nPerformance test complete!")

if __name__ == "__main__":
    test_app_performance()
