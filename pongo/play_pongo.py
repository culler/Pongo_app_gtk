from gi.repository import Gtk, Gdk, WebKit2, Soup
from urllib.parse import urlparse, parse_qs
from . import PongoServer
from .templates import error_template
import re

"""
Implementation of the PlayPongo activity.
"""
spotify = 'https://.*\.spotify\.com'
album_uri = re.compile('spotify:album:([A-z0-9/\+-_]{22})')
album_link = re.compile(spotify + '/album/([A-z0-9/\+-_]{22})')
playlist_uri = re.compile('spotify:user:[^:]*:playlist:([A-z0-9/\+-_]{22})')
playlist_link = re.compile(spotify + '/user/[^:]*/playlist/([A-z0-9/\+-_]{22})')


class PlayPongo(Gtk.Window):
    """
    A WebView window connected to a Pongo server.  This WebView traps connections
    to localhost:8800, which is the redirect address used by Spotify authentication
    for the Pongo Spotify app, as well as urls with path of the form /pongo/*, which
    are consumed as commands to the app itself.
    """
    album_paste_path = 'paste/album/'
    playlist_paste_path = 'paste/playlist/'
    paste_error_path = 'paste/error/'
    
    def __init__(self, app, pongo_server):
        super(Gtk.Window, self).__init__(title='Pongo')
        self.app, self.pongo_server = app, pongo_server
        self.set_default_size(768, 768)
        self.connect("destroy", app.player_destroyed)
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.scroller = scroller = Gtk.ScrolledWindow()
        self.webview = webview = WebKit2.WebView()
        webview.connect("decide-policy", self.navigate)
        webview.connect("load-failed", self.load_error)
        self.cookiejar = WebKit2.CookieManager()
        scroller.add(webview)
        self.box = box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(box)
        box.pack_end(scroller, True, True, 0)
        self.load(pongo_server)
        self.show_all()

    def load(self, pongo_server):
        self.base_url = base_url = 'http://%s/'%self.pongo_server.ip_address
        self.album_paste_url = self.base_url + self.album_paste_path
        self.playlist_paste_url = self.base_url + self.playlist_paste_path
        self.paste_error_url = self.base_url + self.paste_error_path
        self.webview.load_uri(self.base_url + 'albums/')
    
    def navigate(self, view, decision, decision_type):
        """
        Controls navigation through the Pongo pages.
        """
        if decision_type != WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            decision.use()
            return True
        url = decision.get_request().get_uri()
        parts = urlparse(url)
        # Handle Spotify authentication redirects
        if parts.hostname == 'localhost' and parts.port == 8880:
            self.cookiejar.delete_cookies_for_domain('spotify.com')
            query_info = parse_qs(parts.query)
            return_page = query_info['state'][0]
            auth_code = query_info['code'][0]
            url = 'http://%s/spotify_auth/?page=%s;code=%s'%(
                self.pongo_server.ip_address,
                return_page,
                auth_code)
            self.webview.load_uri(url)
            decision.ignore()
            return False
        # Handle app commands
        path = parts.path
        if path.startswith('/pongo/'):
            command = path.split('/')[-1]
            if command == 'paste_link':
                url = self.get_paste_url()
                self.webview.load_uri(url)
            elif command == 'go_back':
                if self.webview.can_go_back:
                    self.webview.go_back()
                else:
                    self.webview.load_uri(self.base_url + 'albums/')
            elif command == 'connect':
                self.app.back_to_finder()
                self.webview.destroy()
                self.hide()
            decision.ignore()
            return False
        decision.use()
        return True

    def get_paste_url(self):
        id = None
        uri = self.clipboard.wait_for_text()
        if id is None:
            match = album_uri.match(uri)
            if match:
                id = match.group(1)
                uri_type = 'album'
        if id is None:
            match = album_link.match(uri)
            if match:
                id = match.group(1)
                uri_type = 'album'
        if id is None:
            match = playlist_uri.match(uri)
            if match:
                id = match.group(1)
                uri_type = 'playlist'
        if id is None:
            match = playlist_link.match(uri)
            if match:
                id = match.group(1)
                uri_type = 'playlist'
        if id is not None and uri_type == 'album':
            return self.album_paste_url + id
        elif id is not None and uri_type == 'playlist':
            return self.playlist_paste_url + id
        else:
            return self.paste_error_url

    def load_error(self, view, frame, uri, error):
        """
        Custom error screen to display when the http connection fails.
        """
        self.webview.load_html(error_template%(self.pongo_server.name, uri))
        return True
