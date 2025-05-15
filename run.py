"""
Run script for Twitter Trend Analysis tool
"""
import os
from app import app

# Ensure output directories exist
RAW_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "raw")
RESULTS_TWEETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets", "results")

os.makedirs(RAW_TWEETS_DIR, exist_ok=True)
os.makedirs(RESULTS_TWEETS_DIR, exist_ok=True)

if __name__ == "__main__":
    print("Starting Twitter Trend Analysis web application...")
    print("Visit http://127.0.0.1:5000 in your browser to use the application")
    # Set threaded=True for better handling of concurrent requests
    app.run(debug=True, threaded=True, host="127.0.0.1", port=5000)
