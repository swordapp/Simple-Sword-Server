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
        return

    def _map_webpy_headers(self, headers):
        return dict([(c[0][5:].replace("_", "-") if c[0].startswith("HTTP_") else c[0].replace("_", "-"), c[1]) for c in headers.items()])
    
    def validate_delete_request(self, section):
        h = HttpHeaders()
        
        # map the headers to standard http
        mapped_headers = self._map_webpy_headers(request.environ)
        ssslog.debug("Validating on header dictionary: " + str(mapped_headers))
        
        try:
            # now validate the http headers
            h.validate(mapped_headers, section)
        except ValidationError as e:
            raise SwordError(error_uri=Errors.bad_request, msg=e.message)
    
    def validate_deposit_request(self, entry_section=None, binary_section=None, multipart_section=None, empty_section=None, allow_multipart=True, allow_empty=False):
        h = HttpHeaders()

        # map the headers to standard http
        mapped_headers = self._map_webpy_headers(request.environ)
        ssslog.debug("Validating on header dictionary: " + str(mapped_headers))
  
        # run the validation
        try:
            # there must be both an "atom" and "payload" input or data in web.data()
            webin = request.POST
            if len(webin) != 2 and len(webin) > 0:
                raise ValidationException("Multipart request does not contain exactly 2 parts")
            if len(webin) >= 2 and not webin.has_key("atom") and not webin.has_key("payload"):
                raise ValidationException("Multipart request must contain Content-Dispositions with names 'atom' and 'payload'")
            if len(webin) > 0 and not allow_multipart:
                raise ValidationException("Multipart request not permitted in this context")
            
            # if we get to here then we have a valid multipart or no multipart
            is_multipart = False
            is_empty = False
            if len(webin) != 2: # if it is not multipart
                # FIXME: this is reading everything in, and should be re-evaluated for performance/scalability
                data = request.environ['wsgi.input'].read(int(request.environ['CONTENT_LENGTH']))
                
                if data is None or data.strip() == "": # FIXME: this does not look safe to scale
                    if allow_empty:
                        ssslog.info("Validating an empty deposit (could be a control operation)")
                        is_empty = True
                    else:
                        raise ValidationException("No content sent to the server")
            else:
                ssslog.info("Validating a multipart deposit")
                is_multipart = True
            
            is_entry = False
            content_type = mapped_headers.get("CONTENT-TYPE")
            if content_type is not None and content_type.startswith("application/atom+xml"):
                ssslog.info("Validating a atom-only deposit")
                is_entry = True
            
            if not is_entry and not is_multipart and not is_empty:
                ssslog.info("Validating a binary deposit")
            
            section = entry_section if is_entry else multipart_section if is_multipart else empty_section if is_empty else binary_section
            
            # now validate the http headers
            h.validate(mapped_headers, section)
            
        except ValidationException as e:
            raise SwordError(error_uri=Errors.bad_request, msg=e.message)
            
    def get_deposit(self, auth=None, atom_only=False):
        # FIXME: this reads files into memory, and therefore does not scale
        # FIXME: this does not deal with the Media Part headers on a multipart deposit
        """
        Take a web.py web object and extract from it the parameters and content required for a SWORD deposit.  This
        includes determining whether this is an Atom Multipart request or not, and extracting the atom/payload where
        appropriate.  It also includes extracting the HTTP headers which are relevant to deposit, and for those not
        supplied providing their defaults in the returned DepositRequest object
        """
        d = DepositRequest()
        
        # map the webpy headers to something more standard
        mapped_headers = self._map_webpy_headers(request.environ)
        
        # get the headers that have been provided.  Any headers which have not been provided will
        # will have default values applied
        h = HttpHeaders()
        d.set_from_headers(h.get_sword_headers(mapped_headers))
        
        if d.content_type.startswith("application/atom+xml"):
            atom_only=True
        
        empty_request = False
        if d.content_length == 0:
            empty_request = True
        if d.content_length > config.max_upload_size:
            raise SwordError(error_uri=Errors.max_upload_size_exceeded, 
                            msg="Max upload size is " + config.max_upload_size + 
                            "; incoming content length was " + str(cl))
        
        # find out if this is a multipart or not
        is_multipart = False
        
        # FIXME: these headers aren't populated yet, because the webpy api doesn't
        # appear to have a mechanism to retrieve them.  urgh.
        entry_part_headers = {}
        media_part_headers = {}
        webin = request.POST
        if len(webin) == 2:
            ssslog.info("Received multipart deposit request")
            d.atom = webin['atom']
            # FIXME: this reads the payload into memory, we need to sort that out
            # read the zip file from the base64 encoded string
            d.content = base64.decodestring(webin['payload'])
            is_multipart = True
        elif not empty_request:
            # if this wasn't a multipart, and isn't an empty request, then the data is in web.data().  This could be a binary deposit or
            # an atom entry deposit - reply on the passed/determined argument to determine which
            if atom_only:
                ssslog.info("Received Entry deposit request")
                # FIXME: this is reading everything in, and should be re-evaluated for performance/scalability
                data = request.environ['wsgi.input'].read(int(request.environ['CONTENT_LENGTH']))
                d.atom = data
            else:
                ssslog.info("Received Binary deposit request")
                # FIXME: this is reading everything in, and should be re-evaluated for performance/scalability
                data = request.environ['wsgi.input'].read(int(request.environ['CONTENT_LENGTH']))
                d.content = data
        
        if is_multipart:
            d.filename = h.extract_filename(media_part_headers)
        else:
            d.filename = h.extract_filename(mapped_headers)
        
        # now just attach the authentication data and return
        d.auth = auth
        return d
        
    def get_delete(self, web, auth=None):
        """
        Take a web.py web object and extract from it the parameters and content required for a SWORD delete request.
        It mainly extracts the HTTP headers which are relevant to delete, and for those not supplied provides thier
        defaults in the returned DeleteRequest object
        """
        d = DeleteRequest()
        
        # map the webpy headers to something more standard
        mapped_headers = self._map_webpy_headers(web.ctx.environ)
        
        h = HttpHeaders()
        d.set_from_headers(h.get_sword_headers(mapped_headers))

        # now just attach the authentication data and return
        d.auth = auth
        return d

    # Request Routing Methods (used by URL Routing)
    ###############################################

    def service_document(self, sub_path=None):
        http_method = request.environ['REQUEST_METHOD']
        if http_method == "GET":
            return self._GET_service_document(sub_path)
        else:
            abort(405, "Method Not Allowed")
            return
    
    def collection(self, path=None): 
        http_method = request.environ['REQUEST_METHOD']
        if http_method == "GET":
            return self._GET_collection(path)
        elif http_method == "POST":
            return self._POST_collection(path)
        else:
            abort(405, "Method Not Allowed")
            return
    
    def media_resource(self, path=None): pass
    def container(self, path=None): pass
    def statement(self, path=None): pass
    
    def aggregation(self, path=None): pass
    def part(self, path=None): pass
    def webui(self, path=None): pass
    
    # SWORD Protocol Operations
    ###########################
    
    def _GET_service_document(self, sub_path=None):
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
    
    def _GET_collection(self, path=None):
        """
        GET a representation of the collection in XML
        Args:
        - collection:   The ID of the collection as specified in the requested URL
        Returns an XML document with some metadata about the collection and the contents of that collection
        """
        ssslog.debug("GET on Collection (list collection contents); Incoming HTTP headers: " + str(request.environ))
        
        # authenticate
        try:
            auth = self.http_basic_authenticate()
        except SwordError as e:
            return self.manage_error(e)

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SwordServer(config, auth)
        cl = ss.list_collection(path)
        response.content_type = "text/xml"
        return cl
        
    def _POST_collection(self, path=None):
        pass
    
    
