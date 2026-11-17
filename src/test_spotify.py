import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Load the variables from the .env file
load_dotenv()

# Set up Spotipy with User Authentication
# The scope 'user-library-read' lets us see your saved tracks
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="user-library-read",
    open_browser=False
))

print("Successfully connected! Fetching your top 3 saved tracks...\n")

# Fetch the user's saved tracks
results = sp.current_user_saved_tracks(limit=3)

# 1. Check that we actually got a response containing 'items'
if results and results.get('items'):
    
    for idx, item in enumerate(results['items']):
        track = item.get('track')
        
        # 2. Tell Pylance we are verifying the track isn't 'None' before digging into it
        if track is not None and track.get('artists'):
            artist_name = track['artists'][0]['name']
            track_name = track.get('name', 'Unknown Track')
            
            print(f"{idx + 1}. {artist_name} - {track_name}")
else:
    print("No tracks found or could not connect to Spotify.")