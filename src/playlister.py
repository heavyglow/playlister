import spotipy
import spotipy.exceptions
from spotipy.oauth2 import SpotifyOAuth
import os
from dotenv import load_dotenv

# Load the variables from the .env file
load_dotenv()

# Set up our connection with the minimum required scope for now
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="playlist-read-private playlist-read-collaborative playlist-modify-private playlist-modify-public",
    open_browser=False
))
print("Successfully connected! Fetching your playlists...\n")
my_profile = sp.current_user()
my_user_id = my_profile['id']
print(f"Connected as: {my_profile['display_name']} (User ID: {my_user_id})\n")
archive_id = "6JytwU5AsQC9OPMKfdIdaG"  # Replace with your actual archive playlist ID

# Function to get the last year of releases from the user's playlists
def get_releases(limit=10000):
    # Make a tiny request just to get the total count
    initial_check = sp.current_user_playlists(limit=1)
    total_playlists = initial_check['total']
    print(f"Total playlists found: {total_playlists}")

    # Check that the archive playlist is accessible and owned by the user
    archive_details = sp.playlist(archive_id)
    if archive_details['owner']['id'] != my_user_id:
        print("Error: The archive playlist is not owned by the current user. Exiting...")
        return

    # We will need variables to handle the batching
    batch_size = 50  # Spotify API returns up to 50 tracks per request

    # This finds the highest multiple of 50 below your total count
    offset = ((total_playlists - 1) // batch_size) * batch_size

    # Load the processed ledger to compare the state of previously processed playlists
    processed_ids = load_processed_ledger()
    
    future_date_streak = 0

    while offset >= 0:
        # Fetch the batch at the current high offset
        results = sp.current_user_playlists(limit=batch_size, offset=offset)
        print(f"Checking playlists {offset} to {offset + batch_size}...")

        # If the 'items' list is empty, we've reached the end!
        if not results['items']:
                break
        
        # Loop through each playlist in this batch
        for playlist in reversed(results['items']):
            # If the owner ID does not match your ID, skip it immediately!
            if playlist['owner']['id'] != my_user_id:
                continue

            # Prevent self-ingestion: If the playlist is the archive itself, skip it
            if playlist['id'] == archive_id:
                continue

            playlist_id = playlist['id']
            playlist_name = playlist['name']

            # If this playlist has already been processed, skip it
            if playlist_id in processed_ids:
                continue

            # Get the added date of the first track in the playlist
            # Wrap the API call in a try-except block
            try:
                # Fetch the items data first
                items_response = sp.playlist_items(playlist_id, limit=1)

                # Safety check: Does the playlist actually have tracks?
                if items_response['items']:
                    # Now it's safe to extract the date
                    playlist_added_at = items_response['items'][0]['added_at']

                    # If we hit 2020 or later, add to the streak
                    if playlist_added_at >= '2020-01-01':
                        future_date_streak += 1
                        if future_date_streak >= 10:
                            print("Found 10 newer playlists in a row. Assuming 2019 is finished! Exiting...")
                            return
                        continue  # Skip to the next playlist without printing
                    
                    # Date check: Look for the specific year-month prefix
                    if playlist_added_at.startswith('2019'):
                        future_date_streak = 0  # Reset the streak!
                        print(f"Found playlist: {playlist_name} added on {playlist_added_at}")
                        # If the transfer is successful, mark it as processed
                        if transfer_tracks(playlist_id):
                            mark_as_processed(playlist_id)

            # If Spotify blocks us, catch the exception and just skip it
            except spotipy.exceptions.SpotifyException as e:
                print(f"Skipped inaccessible playlist: {playlist_name}")

        # Move backwards down the line!
        offset -= batch_size

def load_processed_ledger(filename="processed_playlists.txt"):
    # Create an empty set to hold our IDs
    processed_ids = set()
    
    # Check if the file actually exists first (it won't on the very first run!)
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            # Read each line, strip off the invisible newline characters, and add to the set
            for line in file:
                processed_ids.add(line.strip())
                
    print(f"Loaded {len(processed_ids)} previously processed playlists.")
    return processed_ids

def mark_as_processed(playlist_id, filename="processed_playlists.txt"):
    # Open the file in append mode ('a')
    with open(filename, 'a') as file:
        # Write the ID and a newline character so the next one goes on a new line
        file.write(f"{playlist_id}\n")

def transfer_tracks(source_id, owner_check=my_user_id, limit=100):
    global archive_id  # Ensure we can modify the global archive_id if needed
    # --- PHASE 1: PREPARATION & EXTRACTION ---
    # Check the archive BEFORE we do anything by querying its items directly
    initial_archive_items = sp.playlist_items(archive_id, limit=1)
    
    # Use .get() to safely default to 0 if the total key is missing
    initial_count = initial_archive_items.get('total', 0)
    
    track_uris = []
    offset = 0

    while True:
        # Fetch a batch of tracks from the source playlist
        results = sp.playlist_items(source_id, offset=offset, limit=limit)

        # If the batch is empty, we have successfully grabbed everything!
        if not results['items']:
            break

        # Loop through the playlist entries and grab the URI for each item
        for entry in results['items']:
            track = entry.get('item')
            # Ensure the item exists and has a valid URI before adding
            if track is not None and 'uri' in track:
                track_uris.append(track['uri'])
        
        offset += limit

    print(f"Extracted {len(track_uris)} tracks from the source playlist.")

    # Check if we failed to extract any tracks before injection
    if len(track_uris) == 0:
        print("Warning: 0 tracks extracted from source playlist. Skipping to be safe.")
        return False  # Exit early without deleting anything!

    # Check if adding these tracks will exceed Spotify's 10,000-track limit
    if initial_count + len(track_uris) > 10000:
        print(f"\nArchive playlist is nearly full ({initial_count} tracks) and cannot fit {len(track_uris)} more.")
        archive_id = input("Please create a new archive playlist in Spotify and paste its ID here: ").strip()
        
        # Re-check the initial count for the brand-new archive playlist!
        initial_archive_items = sp.playlist_items(archive_id, limit=1)
        initial_count = initial_archive_items.get('total', 0)

    # --- PHASE 2: INJECTION ---
    # Inject the tracks into the archive playlist in chunks
    for i in range(0, len(track_uris), limit):
        chunk = track_uris[i:i + limit]
        sp.playlist_add_items(archive_id, chunk)

    print(f"Successfully injected {len(track_uris)} tracks into the archive!")

    # --- PHASE 3: VALIDATION & DELETION ---
    # Check the archive AFTER injection
    final_archive_items = sp.playlist_items(archive_id, limit=1)
    final_count = final_archive_items.get('total', 0)

    # Validate that the number of tracks in the archive matches what we expect
    expected_count = initial_count + len(track_uris)

    if final_count == expected_count:
        print("Validation successful! Tracks safely transferred.")
        
        # Now it is safe to delete the source!
        source_playlist_details = sp.playlist(source_id)
        if source_playlist_details['owner']['id'] == owner_check:
            sp.current_user_unfollow_playlist(source_id)
            print("Source playlist successfully deleted.")
            return True
    else:
        print("Validation failed! Track counts or playlist ownership do not match. Skipping deletion.")
        return False  # Validation failed, do not mark as processed

get_releases()