# coding: utf-8
from api import APIClient

# Set your values here
APP_ID = None 
APP_KEY = None
CALLBACK_URL = None

api = APIClient(APP_ID, APP_KEY, redirect_uri=CALLBACK_URL)
print 'Open this url in your browser: %s' % api.get_authorization_url("authorize")
code = raw_input('Enter code parameter in your callback url args: ').strip()
access_token = api.request_access_token(code)
api.set_access_token(access_token['access_token'], access_token['expires_in'])
print api.get.user__get_user_info()

