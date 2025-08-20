# calendar_server.py
# This is the main file for your web service. It contains the server logic
# that will handle requests from ElevenLabs and interact with Google Calendar.

import os
import json
from flask import Flask, request, jsonify, redirect
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from urllib.parse import urlparse, urlunparse

# Define the scopes required to interact with Google Calendar.
# 'calendar.events' allows the app to manage (create, update, delete) events.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
AUTH_TOKEN_FILE = "token.json"

app = Flask(__name__)

# Function to get Google Calendar service.
def get_calendar_service():
    """
    Retrieves the Google Calendar service object using credentials stored
    in a JSON file. This is the secure way to authenticate.
    """
    creds = None
    if os.path.exists(AUTH_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(AUTH_TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Authentication required. Please run the local auth flow first.")
    
    service = build('calendar', 'v3', credentials=creds)
    return service

# MANUAL AUTHENTICATION FLOW for Render
@app.route('/authorize-render')
def authorize_render():
    """
    Step 1: Redirects to Google's OAuth 2.0 consent page to get user's permission.
    This endpoint is for one-time use on the live Render server.
    """
    try:
        redirect_uri = request.url_root.replace('http://', 'https://') + 'oauth2callback-render'
        if os.path.exists('credentials.json'):
            flow = Flow.from_client_secrets_file('credentials.json', scopes=SCOPES, redirect_uri=redirect_uri)
        else:
            creds_info = json.loads(os.environ.get('GOOGLE_CALENDAR_CREDENTIALS'))
            flow = Flow.from_client_config(creds_info, scopes=SCOPES, redirect_uri=redirect_uri)

        authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
        
        # Save the state to the session for later verification.
        # For this one-time use, we can simply pass the state.
        return redirect(authorization_url)
    except Exception as e:
        return jsonify({"error": f"Failed to start authorization flow: {e}"}), 500

@app.route('/oauth2callback-render')
def oauth2callback_render():
    """
    Step 2: Handles the redirect from Google to exchange the authorization code for a token.
    """
    try:
        code = request.args.get('code')
        if not code:
            return "Authorization code not found.", 400

        redirect_uri = request.url_root.replace('http://', 'https://') + 'oauth2callback-render'
        if os.path.exists('credentials.json'):
            flow = Flow.from_client_secrets_file('credentials.json', scopes=SCOPES, redirect_uri=redirect_uri)
        else:
            creds_info = json.loads(os.environ.get('GOOGLE_CALENDAR_CREDENTIALS'))
            flow = Flow.from_client_config(creds_info, scopes=SCOPES, redirect_uri=redirect_uri)
        
        flow.fetch_token(code=code)
        
        # Save the credentials to a temporary file, which you will then download.
        with open(AUTH_TOKEN_FILE, 'w') as token:
            token.write(flow.credentials.to_json())
        
        return "Authentication successful! The token.json file has been created. You can now download this file from Render and upload its content as an environment variable."
    except Exception as e:
        return jsonify({"error": f"Failed to get token: {e}"}), 500


# Main endpoint to handle scheduling requests from ElevenLabs.
@app.route('/schedule-appointment', methods=['POST'])
def schedule_appointment():
    """
    An API endpoint that takes appointment details and creates a new
    event in the user's Google Calendar.
    """
    try:
        # Parse the JSON payload from the request.
        data = request.json
        summary = data.get('summary', 'New AI Agent Consultation')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        calendar_id = 'primary' # You can make this configurable if needed.

        # Basic validation of the incoming data.
        if not start_time or not end_time:
            return jsonify({"error": "Missing start_time or end_time."}), 400

        service = get_calendar_service()

        # Build the event body for the Google Calendar API.
        event = {
            'summary': summary,
            'location': 'Client Call',
            'description': 'Scheduled by AdiuvansAI Agent.',
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/New_York', # Set to your desired timezone.
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/New_York',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        # Call the Google Calendar API to insert the event.
        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        
        # Return a success message with details of the created event.
        return jsonify({
            "status": "success",
            "message": "Appointment scheduled successfully.",
            "event_link": event.get('htmlLink')
        }), 200

    except HttpError as e:
        return jsonify({"error": f"Google Calendar API Error: {e.content.decode()}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # When running locally, you'll need to handle the port.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
