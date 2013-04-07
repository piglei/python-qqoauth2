#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python SDK for Tencent qq
~~~~~~~~~~~~~~~~~~~~~~~~~

Simple wrapper for qq oauth2(http://opensns.qq.com/)

Inspired by liaoxuefeng(http://michaelliao.github.com/sinaweibopy/)

author: piglei2007@gmail.com
"""

__VERSION__ = [1, 0, 0]
QQ_DOMAIN = 'graph.qq.com'

try:
    import json
except ImportError:
    import simplejson as json
import time
import urllib
import urllib2
import logging
import urlparse

# urllib raise an excepition for 400 status, need to add
# an extra opener
class BetterHTTPErrorProcessor(urllib2.BaseHandler):
    def http_error_400(self, request, response, code, msg, hdrs):
        return response
    def http_error_403(self, request, response, code, msg, hdrs):
        return response

opener = urllib2.build_opener(BetterHTTPErrorProcessor)
urllib2.install_opener(opener)

class QQBaseException(Exception):
    """
    Base Exception
    """
    pass

class QQAPIError(QQBaseException):
    """
    raise APIError if got failed json message.
    """
    def __init__(self, error_code, error):
        self.error_code = error_code
        self.error = error
        super(QQAPIError, self).__init__(self, error)

    def __str__(self):
        return 'QQAPIError: %s: %s' % (self.error_code, self.error)

class FancyDict(dict):
    def __getattr__(self, key): 
        try:
            return self[key]
        except KeyError, k:
            raise AttributeError, k

    def __setattr__(self, key, value): 
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError, k:
            raise AttributeError, k

def _encode_params(**kw):
    '''
    Encode parameters.
    '''
    args = []
    for k, v in kw.iteritems():
        qv = v.encode('utf-8') if isinstance(v, unicode) else str(v)
        args.append('%s=%s' % (k, urllib.quote(qv)))
    return '&'.join(args)

def _encode_multipart(**kw):
    '''
    Build a multipart/form-data body with generated random boundary.
    '''
    boundary = '----------%s' % hex(int(time.time() * 1000))
    data = []
    for k, v in kw.iteritems():
        data.append('--%s' % boundary)
        if hasattr(v, 'read'):
            # file-like object:
            ext = ''
            filename = getattr(v, 'name', '')
            n = filename.rfind('.')
            if n != (-1):
                ext = filename[n:].lower()
            content = v.read()
            data.append('Content-Disposition: form-data; name="%s"; filename="hidden"' % k)
            data.append('Content-Length: %d' % len(content))
            data.append('Content-Type: %s\r\n' % _guess_content_type(ext))
            data.append(content)
        else:
            data.append('Content-Disposition: form-data; name="%s"\r\n' % k)
            data.append(v.encode('utf-8') if isinstance(v, unicode) else v)
    data.append('--%s--\r\n' % boundary)
    return '\r\n'.join(data), boundary

_CONTENT_TYPES = { '.png': 'image/png', '.gif': 'image/gif', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.jpe': 'image/jpeg' }

def _guess_content_type(ext):
    return _CONTENT_TYPES.get(ext, 'application/octet-stream')

_HTTP_GET = 0
_HTTP_POST = 1
_HTTP_UPLOAD = 2

def _http_get(_url, authorization=None, **kw):
    logging.info('GET %s' % _url)
    return _http_call(_url, _HTTP_GET, authorization, **kw)

def _http_post(_url, authorization=None, **kw):
    logging.info('POST %s' % _url)
    return _http_call(_url, _HTTP_POST, authorization, **kw)

def _http_upload(_url, authorization=None, **kw):
    logging.info('MULTIPART POST %s' % _url)
    return _http_call(_url, _HTTP_UPLOAD, authorization, **kw)

COMMON_ARGS = ('access_token', 'oauth_consumer_key', 'openid', 'format')

def _http_call(_url, method, authorization, **kw):
    """
    send an http request and expect to return a json object if no error.
    """
    params = None
    boundary = None
    if authorization:
        kw.update(access_token=authorization)

    # Common args should always as get args
    if method != _HTTP_GET:
        params = {}
        for arg in COMMON_ARGS:
            params[arg] = kw.get(arg, '')

    if method==_HTTP_UPLOAD:
        params, boundary = _encode_multipart(**kw)
    else:
        params = _encode_params(**kw)

    http_url = '%s?%s' % (_url, params)

    http_body = None if method==_HTTP_GET else params
    req = urllib2.Request(http_url, data=http_body)
    if boundary:
        req.add_header('Content-Type', 'multipart/form-data; boundary=%s' % boundary)
    resp = urllib2.urlopen(req)
    body = resp.read()
    # body may startwith "callback"
    if body.startswith('callback( '):
        body = body[10:-3]

    try:
        body = FancyDict(json.loads(body))
    except:
        body = body
    if not isinstance(body, basestring):
        if 'error' in body:
            raise QQAPIError(body.error, getattr(body, 'error_description', ''))
        if 'ret' in body and body.ret != 0:
            raise QQAPIError(body.ret, getattr(body, 'msg', ''))
    return body

class HttpObject(object):
    def __init__(self, client, method):
        self.client = client
        self.method = method

    def __getattr__(self, attr):
        def wrap(**kw):
            if self.client.is_expires():
                raise QQAPIError('100015', 'access token is revoked')

            openid = self.client.get_openid()
            return _http_call(
                '%s%s' % (self.client.api_url, attr.replace('__', '/')),
                self.method, 
                self.client.access_token,
                oauth_consumer_key=self.client.app_id, 
                format='json', 
                openid=openid,
                **kw
            )
        return wrap

class APIClient(object):
    """
    Api Client
    """
    def __init__(self, app_id, app_key, redirect_uri=None, response_type='code'):
        self.app_id = app_id
        self.app_key = app_key
        self.redirect_uri = redirect_uri
        self.response_type = response_type
        self.auth_url = 'https://%s/oauth2.0/' % QQ_DOMAIN
        self.api_url = 'https://%s/' % QQ_DOMAIN
        self.access_token = None
        self.openid = None
        self.expires = 0.0
        self.get = HttpObject(self, _HTTP_GET)
        self.post = HttpObject(self, _HTTP_POST)
        self.upload = HttpObject(self, _HTTP_UPLOAD)

    def set_access_token(self, access_token, expires_in):
        self.access_token = str(access_token)
        self.expires = float(expires_in)
        self.openid = None

    def get_authorize_url(self, redirect_uri=None, display=None, response_type='code', endpoint='authorize', 
                          scopes=[], state=None):
        '''
        return the authroize url that should be redirect.
        '''
        redirect = redirect_uri if redirect_uri else self.redirect_uri
        if not redirect:
            raise QQBaseException('Redirect uri is needed.')
      
        state = state if state is not None else 'default_state'
        args = dict(
            client_id = self.app_id,
            response_type = response_type,
            redirect_uri = redirect,
            scope = ','.join(scopes),
            state = state
        )
        if display:
            args.update(display=display)
        return '%s%s?%s' % (self.auth_url, endpoint, _encode_params(**args))

    def get_authorization_url(self, endpoint, **kwargs):
        """
        compatible with others
        """
        kwargs.update(endpoint=endpoint)
        return self.get_authorize_url(**kwargs)

    def request_access_token(self, code, redirect_uri=None, grant_type='authorization_code', endpoint='token'):
        """
        return access token as object: {"access_token":"your-access-token","expires_in":12345678}
        expires_in is standard unix-epoch-time
        """
        redirect = redirect_uri if redirect_uri else self.redirect_uri
        if not redirect:
            raise QQBaseException('Redirect uri is needed.')

        ret = _http_get('%s%s' % (self.auth_url, endpoint),
                client_id = self.app_id,
                client_secret = self.app_key,
                redirect_uri = redirect,
                code = code, grant_type = grant_type)
        # ret is a string like this: "access_token=C8F28A60779B94518AF86E1FE8D92312&expires_in=7776000"
        ret = FancyDict(dict((k, v[0]) for k, v in urlparse.parse_qs(ret).items()))
        ret['expires_in'] = float(ret['expires_in']) + time.time()
        return ret

    def get_access_token(self, endpoint, **kwargs):
        """
        compatible with others
        """
        kwargs.update(endpoint=endpoint)
        code = kwargs.pop('code', None)
        access_token =  self.request_access_token(code, **kwargs)
        access_token = FancyDict(access_token)
        access_token['expire_time'] = access_token.expires_in
        access_token['refresh_token'] = ''
        return access_token

    def get_openid(self):
        """
        https://graph.qq.com/oauth2.0/me?access_token=YOUR_ACCESS_TOKEN
        """
        if not self.openid:
            if self.is_expires():
                raise QQBaseException('Your muse set a correct access token to request an openid')
            ret = _http_get('%s%s' % (self.auth_url, 'me'), authorization = self.access_token)
            self.openid = ret.openid
        return self.openid

    def is_expires(self):
        return not self.access_token or time.time() > self.expires

    def __getattr__(self, attr):
        return getattr(self.get, attr)

