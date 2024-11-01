from config import strava_id, strava_secret, bot_token
import requests
from urllib.parse import urlencode
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio
import time
import json
import os
#from keep_alive import keep_alive

# variables
#strava_id = os.environ['STRAVA_ID']
#strava_secret = os.environ['STRAVA_SECRET']
#bot_token = os.environ['BOT_TOKEN']

# Strava API Configuration URLs and Endpoints
url = 'https://www.strava.com/api/v3/'
authorization_url = 'https://www.strava.com/oauth/authorize'
redirect_uri = 'http://localhost:8080/callback'
scope = 'read_all,activity:read_all,profile:read_all'
token_url = 'https://www.strava.com/oauth/token'

# Dictionaries to manage user states
waiting_for_auth_code = {}  # Track users waiting for authorization code
authorized_users = {}  # Store authorized users' access tokens
athlete_id = None

def generate_authorization_url():
    authorize_params = {
        'client_id': strava_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': scope,
    }
    return f'{authorization_url}?{urlencode(authorize_params)}'

def refresh_access_token(client_id, client_secret, message_chat_id):
    print(f"\n=== Refresh Token Debug ===")
    print(f"Chat ID: {message_chat_id}")
    #print(f"Current authorized_users state: {json.dumps(authorized_users, indent=2)}")

    tokens = authorized_users.get(message_chat_id, {})
    #print(f"Tokens for user: {json.dumps(tokens, indent=2)}")

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
        #print(f"Refresh response body: {response.text}")

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
            #print(f"New tokens: {json.dumps(authorized_users[message_chat_id], indent=2)}")
        else:
            print("Failed to refresh token.")
            return None
    else:
        print("Token still valid, using existing access token")

    return access_token

# Initialize bot and dispatcher
dp = Dispatcher()

#Start command
@dp.message(Command("start"))
async def start(message: types.Message):
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

#handle the auth code after start command
@dp.message(lambda message: waiting_for_auth_code.get(message.chat.id, False))
async def handle_auth_code(message: types.Message):
    print(f"\n=== Message Handler Debug ===")
    print(f"Chat ID: {message.chat.id}")
    print(f"Message text: {message.text}")

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
    #print(f"Token response body: {token_response.text}")

    if token_response.status_code == 200:
        data = token_response.json()
        authorized_users[message.chat.id] = {
            "access_token": data['access_token'],
            "refresh_token": data['refresh_token'],
            "expires_at": data['expires_at']
        }
        #print(f"Authorization successful. Token stored: {json.dumps(authorized_users[message.chat.id], indent=2)}")

        global athlete_id
        athlete_id = data.get('athlete', {}).get('id', None)

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

#Activities command
@dp.message(Command("activities"))
async def activities(message: types.Message):
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

    print("Requesting activities from Strava...")
    response = requests.get(activities_url, headers=headers)

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

#Stats command
@dp.message(Command("stats"))
async def stats(message: types.Message):
    if athlete_id is not None:
        print(f"\n=== Stats Command Debug ===")
        print(f"Chat ID: {message.chat.id}")

        if message.chat.id not in authorized_users:
            print("User not authorized")
            await message.reply("Please use /start command to authorize first.")
            return

        access_token = refresh_access_token(strava_id, strava_secret, message.chat.id)

        if not access_token:
            print("Failed to get access token")
            await message.reply("Failed to refresh access token. Please reauthorize with /start command.")
            return

        activities_url = f'{url}athletes/{athlete_id}/stats'
        headers = {'Authorization': f'Bearer {access_token}'}

        response = requests.get(activities_url, headers=headers)

        if response.status_code == 200:
            stats = response.json()
            stats_message = (
                f"🏃‍♂️ Your Activity stats:\n"
                f"biggest_ride_distance: {stats.get('biggest_ride_distance', '')}\n"
                f"biggest_climb_elevation_gain: {stats.get('biggest_climb_elevation_gain', '')}\n"
            )
            await message.reply(stats_message)
        else:
            await message.reply("Failed to retrieve athlete information. Please try again later.")
    else:
        await message.reply("Please use /start command to authorize first.")

#Athelte command
@dp.message(Command("athlete"))
async def athlete(message: types.Message):
    print(f"\n=== Athlete Command Debug ===")
    print(f"Chat ID: {message.chat.id}")

    if message.chat.id not in authorized_users:
        print("User not authorized")
        await message.reply("Please use /start command to authorize first.")
        return

    access_token = refresh_access_token(strava_id, strava_secret, message.chat.id)

    if not access_token:
        print("Failed to get access token")
        await message.reply("Failed to refresh access token. Please reauthorize with /start command.")
        return

    athlete_url = f'{url}athlete'
    headers = {'Authorization': f'Bearer {access_token}'}

    response = requests.get(athlete_url, headers=headers)

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
        await message.reply("Failed to retrieve athlete information. Please try again later.")

#Zones command
@dp.message(Command("zones"))
async def zones(message: types.Message):
    print(f"\n=== Zones Command Debug ===")
    print(f"Chat ID: {message.chat.id}")

    if message.chat.id not in authorized_users:
        print("User not authorized")
        await message.reply("Please use /start command to authorize first.")
        return

    access_token = refresh_access_token(strava_id, strava_secret, message.chat.id)

    if not access_token:
        print("Failed to get access token")
        await message.reply("Failed to refresh access token. Please reauthorize with /start command.")
        return

    zones_url = f'{url}athlete/zones'
    headers = {'Authorization': f'Bearer {access_token}'}

    response = requests.get(zones_url, headers=headers)

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
        await message.reply("Failed to retrieve zones information. Please try again later.")

print("=== Bot Starting ===")
print(f"Initial state:")
print(f"waiting_for_auth_code: {waiting_for_auth_code}")
print(f"authorized_users: {authorized_users}")

# Keep the web server alive 
#keep_alive()

async def main():
    bot = Bot(token=bot_token)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


