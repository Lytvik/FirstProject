import json
import os

from django.shortcuts import render, redirect
from django.http import HttpResponse
from TripJournal.settings import MEDIA_ROOT
from trip_journal_app.utils import (
    saved_stories, unicode_slugify, load_story_info
)

import random
import string
from apiclient.discovery import build

from flask import Flask
from flask import make_response
from flask import render_template
from flask import request
from flask import session

import httplib2
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError

from simplekv.memory import DictStore
from flaskext.kvsession import KVSessionExtension


# Create your views here.


'''def home(request):
    
    #Home page view.
    
    stories = []
    for story in saved_stories():
        stories += [{'url': story,
                    'title': load_story_info(story)['title']}]
    return render(request, 'index.html', {'stories': stories}) '''


def edit(request, story_name):
    
    #Edit page view. When changes on the page are published
    #saves added content to file in media directory.
    

    # POST requests for publishing
    if request.method == 'POST':
        request_body = json.loads(request.body)
        story_title_slug = unicode_slugify(request_body['title'])
        file_name = os.path.join(MEDIA_ROOT, story_title_slug + '.json')
        with open(file_name, 'w') as story_file:
            json.dump(request_body, story_file)
        return HttpResponse("ok")

    # GET requests
    elif request.method == 'GET':

        # for cases when there is no name or it's a new story
        story_info = {'title': story_name}
        if story_name:
            slugish_name = unicode_slugify(story_name)
            if slugish_name in saved_stories():

                # redirect to normal url
                if slugish_name != story_name:
                    return redirect('/edit/%s' % slugish_name)

                story_info = load_story_info(story_name)

        return render(request, 'edit.html', story_info)


app = Flask(__name__)
app.secret_key = ''.join(random.choice(string.ascii_uppercase + string.digits)
                         for x in xrange(32))


# See the simplekv documentation for details
store = DictStore()


# This will replace the app's session handling
KVSessionExtension(store, app)


# Update client_secrets.json with your Google API project information.
# Do not change this assignment.
CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
SERVICE = build('plus', 'v1')


#@app.route('/', methods=['GET'])
def index():
    """Initialize a session for the current user, and render index.html."""
    # Create a state token to prevent request forgery.
    # Store it in the session for later validation.
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    session['state'] = state
    # Set the Client ID, Token State, and Application Name in the HTML while
    # serving it.
    response = make_response(
        render_template('index.html',
                        CLIENT_ID=CLIENT_ID,
                        STATE=state,
                        APPLICATION_NAME=APPLICATION_NAME))
    response.headers['Content-Type'] = 'text/html'
    return response


#@app.route('/connect', methods=['POST'])
def connect():
    """Exchange the one-time authorization code for a token and
    store the token in the session."""
    # Ensure that the request is not a forgery and that the user sending
    # this connect request is the expected user.
    if request.args.get('state', '') != session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Normally, the state is a one-time token; however, in this example,
    # we want the user to be able to connect and disconnect
    # without reloading the page.  Thus, for demonstration, we don't
    # implement this best practice.
    # del session['state']

    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # An ID Token is a cryptographically-signed JSON object encoded in base 64.
    # Normally, it is critical that you validate an ID Token before you use it,
    # but since you are communicating directly with Google over an
    # intermediary-free HTTPS channel and using your Client Secret to
    # authenticate yourself to Google, you can be confident that the token you
    # receive really comes from Google and is valid. If your server passes the
    # ID Token to other components of your app, it is extremely important that
    # the other components validate the token before using it.
    gplus_id = credentials.id_token['sub']

    stored_credentials = session.get('credentials')
    stored_gplus_id = session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Store the access token in the session for later use.
    session['credentials'] = credentials
    session['gplus_id'] = gplus_id
    response = make_response(json.dumps('Successfully connected user.', 200))
    response.headers['Content-Type'] = 'application/json'
    return response


#@app.route('/disconnect', methods=['POST'])
def disconnect():
    """Revoke current user's token and reset their session."""

    # Only disconnect a connected user.
    credentials = session.get('credentials')
    if credentials is None:
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Execute HTTP GET request to revoke current token.
    access_token = credentials.access_token
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's session.
        del session['credentials']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


#@app.route('/people', methods=['GET'])
def people():
    """Get list of people user has shared with this app."""
    credentials = session.get('credentials')
    # Only fetch a list of people for connected users.
    if credentials is None:
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    try:
        # Create a new authorized API client.
        http = httplib2.Http()
        http = credentials.authorize(http)
        # Get a list of people that this user has shared with this app.
        google_request = SERVICE.people().list(userId='me', collection='visible')
        result = google_request.execute(http=http)

        response = make_response(json.dumps(result), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    except AccessTokenRefreshError:
        response = make_response(json.dumps('Failed to refresh access token.'), 500)
        response.headers['Content-Type'] = 'application/json'
        return response


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=4567)
