from pylons import request, response, session, tmpl_context as c
from pylons.controllers.util import abort, redirect_to
from pylons.controllers import WSGIController
from pylons.templating import render_mako as render

import re, base64, urllib, uuid
from core import Auth, SWORDSpec, SwordError, AuthException, DepositRequest, DeleteRequest
from negotiator import ContentNegotiator, AcceptParameters, ContentType
from spec import Errors, HttpHeaders, ValidationException

import logging
ssslog = logging.getLogger(__name__)

# create the global configuration and import the implementation classes
from sss import Configuration
config = Configuration()
Authenticator = config.get_authenticator_implementation()
SwordServer = config.get_server_implementation()

__controller__ = "SwordController"

HEADER_MAP = {
    HttpHeaders.in_progress : "HTTP_IN_PROGRESS",
    HttpHeaders.metadata_relevant : "HTTP_METADATA_RELEVANT",
    HttpHeaders.on_behalf_of : "HTTP_ON_BEHALF_OF"
}

class SwordController(WSGIController):

    # WSGI Controller Stuff
    #######################

    def __call__(self, environ, start_response):
        """Invoke the Controller"""
        # WSGIController.__call__ dispatches to the Controller method
        # the request is routed to. This routing information is
        # available in environ['pylons.routes_dict']
        return WSGIController.__call__(self, environ, start_response)

    # Generically useful methods
    ############################

    def http_basic_authenticate(self):
        # extract the appropriate HTTP headers
        auth_header = request.environ.get('HTTP_AUTHORIZATION')
        obo = request.environ.get(HEADER_MAP[HttpHeaders.on_behalf_of])

        # if we're not supplied with an auth header, bounce
        if auth_header is None:
            ssslog.info("No auth header supplied; will return 401 with SSS realm")
            response.headers['WWW-Authenticate'] = 'Basic realm="SSS"'
            raise SwordError(status=401, empty=True)
        
        # deconstruct the BASIC auth header
        try:
            auth_header = re.sub('^Basic ', '', auth_header)
            username, password = base64.decodestring(auth_header).split(':')
            ssslog.debug("successfully interpreted Basic Auth header")
        except Exception as e:
            # could be exceptions in either decoding the header or in doing a split
            ssslog.error("unable to interpret authentication header: " + auth_header)
            raise SwordError(error_uri=Errors.bad_request, msg="unable to interpret authentication header")
        
        ssslog.info("Authentication details: " + str(username) + ":" + str(password) + "; On Behalf Of: " + str(obo))

        authenticator = Authenticator(config)
        try:
            auth = authenticator.basic_authenticate(username, password, obo)
        except AuthException as e:
            if e.authentication_failed:
                raise SwordError(status=401, empty=True)
            elif e.target_owner_unknown:
                raise SwordError(error_uri=Errors.target_owner_unknown, msg="unknown user " + str(obo) + " as on behalf of user")
        
        return auth
    
    def manage_error(self, sword_error):
        response.status_int = sword_error.status
        ssslog.info("Returning error status: " + str(sword_error.status))
        if not sword_error.empty:
            response.content_type = "text/xml"
            return sword_error.error_document
        return ""

    # SWORD Protocol Operations
    ###########################

    def service_document(self, sub_path=None):
        """ 
        GET the service document - returns an XML document 
        - sub_path - the path provided for the sub-service document
        """
        ssslog.debug("GET on Service Document (retrieve service document); Incoming HTTP headers: " + str(request.environ))
        
        # authenticate
        try:
            auth = self.http_basic_authenticate()
        except SwordError as e:
            return self.manage_error(e)

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SwordServer(config, auth)
        sd = ss.service_document(sub_path)
        response.content_type = "text/xml"
        return sd
