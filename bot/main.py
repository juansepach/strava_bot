from config import strava_id, strava_secret, api_id, api_hash, bot_token  
import requests
from urllib.parse import urlencode
from pyrogram import Client, filters
import time
import json

# Strava API Configuration URLs and Endpoints
url = 'https://www.strava.com/api/v3/'
authorization_url = 'https://www.strava.com/oauth/authorize'
redirect_uri = 'http://localhost:8080/callback'
scope = 'read_all,activity:read_all,profile:read_all'
token_url = 'https://www.strava.com/oauth/token'

# Dictionaries to manage user states
waiting_for_auth_code = {}  # Track users waiting for authorization code
authorized_users = {}  # Store authorized users' access tokens

def generate_authorization_url():
    authorize_params = {
        'client_id': strava_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': scope,
    }
    return f'{authorization_url}?{urlencode(authorize_params)}'

def refresh_access_token(client_id, client_secret, message_chat_id):
    """Refreshes the Strava access token if expired for a given user."""
    print(f"\n=== Refresh Token Debug ===")
    print(f"Chat ID: {message_chat_id}")
    print(f"Current authorized_users state: {json.dumps(authorized_users, indent=2)}")
    
    tokens = authorized_users.get(message_chat_id, {})
    print(f"Tokens for user: {json.dumps(tokens, indent=2)}")
    
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at", 0)

    print(f"Current time: {time.time()}")
    print(f"Token expires at: {expires_at}")

    if time.time() >= expires_at:
        print("Token expired. Attempting to refresh...")
        response = requests.post(token_url, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        })
        print(f"Refresh response status: {response.status_code}")
        print(f"Refresh response body: {response.text}")
        
        if response.status_code == 200:
            new_tokens = response.json()
            access_token = new_tokens["access_token"]
            refresh_token = new_tokens["refresh_token"]
            expires_at = new_tokens["expires_at"]

            authorized_users[message_chat_id] = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at
            }
            print("Token refreshed successfully.")
            print(f"New tokens: {json.dumps(authorized_users[message_chat_id], indent=2)}")
        else:
            print("Failed to refresh token.")
            return None
    else:
        print("Token still valid, using existing access token")
    
    return access_token

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

@app.on_message(filters.command('start') & filters.private)
async def start(client, message):
    """Sends the authorization URL if the user is not already authorized."""
    print(f"\n=== Start Command Debug ===")
    print(f"Chat ID: {message.chat.id}")
    print(f"User is authorized: {message.chat.id in authorized_users}")
    
    if message.chat.id in authorized_users:
        await message.reply('You are already authorized! You can use /activities, /stats, /athlete, or /zones commands.')
    else:
        authorize_url = generate_authorization_url()
        waiting_for_auth_code[message.chat.id] = True
        print(f"Setting waiting_for_auth_code for chat {message.chat.id}")
        print(f"Current waiting_for_auth_code state: {waiting_for_auth_code}")
        
        await message.reply(
            f'Hello! To authorize this app with Strava, click the following link:\n{authorize_url}\n\n'
            f'After authorizing, copy the authorization code from the URL and send it back to this chat.'
        )

@app.on_message(filters.text & filters.private & ~filters.regex(r'^/'))  # Changed to use regex filter
async def handle_messages(client, message):
    """Handler for text messages, including authorization code."""
    print(f"\n=== Message Handler Debug ===")
    print(f"Chat ID: {message.chat.id}")
    print(f"Message text: {message.text}")
    print(f"Is waiting for auth code: {waiting_for_auth_code.get(message.chat.id)}")
    
    # Only process the message as an auth code if we're waiting for one
    if waiting_for_auth_code.get(message.chat.id):
        print("Processing potential authorization code")
        authorization_code = message.text.strip()
        token_params = {
            'client_id': strava_id,
            'client_secret': strava_secret,
            'code': authorization_code,
            'grant_type': 'authorization_code',
        }
        
        print("Requesting token from Strava...")
        token_response = requests.post(token_url, data=token_params)
        print(f"Token response status: {token_response.status_code}")
        print(f"Token response body: {token_response.text}")
        
        if token_response.status_code == 200:
            data = token_response.json()
            authorized_users[message.chat.id] = {
                "access_token": data['access_token'],
                "refresh_token": data['refresh_token'],
                "expires_at": data['expires_at']
            }
            print(f"Authorization successful. Token stored: {json.dumps(authorized_users[message.chat.id], indent=2)}")
            
            # Remove the waiting state AFTER successful authorization
            waiting_for_auth_code.pop(message.chat.id, None)
            print(f"Updated waiting_for_auth_code state: {waiting_for_auth_code}")
            
            await message.reply(
                'Authorization successful! You can now use the following commands:\n'
                '/activities - View your activities\n'
                '/stats - View your statistics\n'
                '/athlete - View your profile\n'
                '/zones - View your heart rate zones'
            )
        else:
            print("Authorization failed")
            await message.reply('Authorization failed. Please try again with /start command.')

@app.on_message(filters.command('activities') & filters.private)
async def activities(client, message):
    """Fetches and sends the user's Strava activities if authorized."""
    print(f"\n=== Activities Command Debug ===")
    print(f"Chat ID: {message.chat.id}")
    print(f"Is user authorized: {message.chat.id in authorized_users}")
    
    if message.chat.id not in authorized_users:
        print("User not authorized")
        await message.reply("Please use /start command to authorize first.")
        return

    access_token = refresh_access_token(strava_id, strava_secret, message.chat.id)
    print(f"Retrieved access token: {access_token is not None}")
    
    if not access_token:
        print("Failed to get access token")
        await message.reply("Failed to refresh access token. Please reauthorize with /start command.")
        return

    activities_url = f'{url}athlete/activities'
    headers = {'Authorization': f'Bearer {access_token}'}
    
    print(f"Requesting activities from Strava...")
    print(f"URL: {activities_url}")
    print(f"Headers: {headers}")
    
    response = requests.get(activities_url, headers=headers)
    print(f"Activities response status: {response.status_code}")
    print(f"Activities response body: {response.text[:500]}...")  # Print first 500 chars to avoid huge logs

    if response.status_code == 200:
        activities = response.json()
        print(f"Number of activities received: {len(activities)}")
        
        if not activities:
            await message.reply("No activities found.")
            return
            
        activity_message = 'Your recent Strava activities:\n'
        for activity in activities[:10]:
            distance_km = round(activity['distance'] / 1000, 2)
            activity_message += f"• {activity['name']} - {distance_km}km\n"
        await message.reply(activity_message)
    else:
        print(f"Failed to get activities. Status code: {response.status_code}")
        await message.reply("Failed to retrieve activities. Please try again later.")

@app.on_message(filters.command('athlete') & filters.private)
async def athlete(client, message):
    """Fetches and sends the user's Strava profile if authorized."""
    print(f"\n=== Athlete Command Debug ===")
    print(f"Chat ID: {message.chat.id}")
    print(f"Is user authorized: {message.chat.id in authorized_users}")
    
    if message.chat.id not in authorized_users:
        print("User not authorized")
        await message.reply("Please use /start command to authorize first.")
        return

    access_token = refresh_access_token(strava_id, strava_secret, message.chat.id)
    print(f"Retrieved access token: {access_token is not None}")
    
    if not access_token:
        print("Failed to get access token")
        await message.reply("Failed to refresh access token. Please reauthorize with /start command.")
        return

    athlete_url = f'{url}athlete'
    headers = {'Authorization': f'Bearer {access_token}'}
    
    print(f"Requesting athlete info from Strava...")
    print(f"URL: {athlete_url}")
    print(f"Headers: {headers}")
    
    response = requests.get(athlete_url, headers=headers)
    print(f"Athlete response status: {response.status_code}")
    print(f"Athlete response body: {response.text}")

    if response.status_code == 200:
        athlete = response.json()
        athlete_message = (
            f"🏃‍♂️ Your Strava Profile:\n"
            f"Name: {athlete.get('firstname', '')} {athlete.get('lastname', '')}\n"
            f"Username: {athlete.get('username', 'Not set')}\n"
            f"City: {athlete.get('city', 'Not set')}\n"
            f"Country: {athlete.get('country', 'Not set')}\n"
            f"Weight: {athlete.get('weight', 'Not set')}kg"
        )
        await message.reply(athlete_message)
    else:
        print(f"Failed to get athlete info. Status code: {response.status_code}")
        await message.reply("Failed to retrieve athlete information. Please try again later.")

@app.on_message(filters.command('zones') & filters.private)
async def zones(client, message):
    """Fetches and sends the user's Strava zones if authorized."""
    print(f"\n=== Zones Command Debug ===")
    print(f"Chat ID: {message.chat.id}")
    print(f"Is user authorized: {message.chat.id in authorized_users}")
    
    if message.chat.id not in authorized_users:
        print("User not authorized")
        await message.reply("Please use /start command to authorize first.")
        return

    access_token = refresh_access_token(strava_id, strava_secret, message.chat.id)
    print(f"Retrieved access token: {access_token is not None}")
    
    if not access_token:
        print("Failed to get access token")
        await message.reply("Failed to refresh access token. Please reauthorize with /start command.")
        return

    zones_url = f'{url}athlete/zones'
    headers = {'Authorization': f'Bearer {access_token}'}
    
    print(f"Requesting zones from Strava...")
    print(f"URL: {zones_url}")
    print(f"Headers: {headers}")
    
    response = requests.get(zones_url, headers=headers)
    print(f"Zones response status: {response.status_code}")
    print(f"Zones response body: {response.text}")

    if response.status_code == 200:
        zones_data = response.json()
        if 'heart_rate' in zones_data:
            zones_message = "❤️ Your Heart Rate Zones:\n"
            for i, zone in enumerate(zones_data['heart_rate']['zones'], 1):
                zones_message += f"Zone {i}: {zone['min']} - {zone.get('max', 'max')} bpm\n"
            await message.reply(zones_message)
        else:
            print("No heart rate zones found in response")
            await message.reply("No heart rate zones found in your profile.")
    else:
        print(f"Failed to get zones. Status code: {response.status_code}")
        await message.reply("Failed to retrieve zones information. Please try again later.")

print("=== Bot Starting ===")
print(f"Initial state:")
print(f"waiting_for_auth_code: {waiting_for_auth_code}")
print(f"authorized_users: {authorized_users}")
app.run()