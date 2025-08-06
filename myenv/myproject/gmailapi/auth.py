import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
from django.conf import settings
from google_auth_oauthlib.flow import Flow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
print("JSON Path:", os.path.join(settings.BASE_DIR, 'credentials.json'))

def get_flow():
    flow = Flow.from_client_secrets_file(
        os.path.join(settings.BASE_DIR, 'credentials.json'),  # this resolves to correct path
        scopes=SCOPES,
        redirect_uri='http://localhost:8000/oauth2callback/'
    )
    return flow
