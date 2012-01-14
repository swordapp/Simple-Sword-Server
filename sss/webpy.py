import web, re, base64, urllib, uuid
from web.wsgiserver import CherryPyWSGIServer
from core import Auth, SWORDSpec, SwordError, AuthException, DepositRequest, DeleteRequest
from negotiator import ContentNegotiator, AcceptParameters, ContentType
from webui import HomePage, CollectionPage, ItemPage
from spec import Errors, HttpHeaders, ValidationException

from sss_logging import logging
ssslog = logging.getLogger(__name__)

# create the global configuration and import the implementation classes
from config import Configuration
config = Configuration()
Authenticator = config.get_authenticator_implementation()
SwordServer = config.get_server_implementation()

# Whether to run using SSL.  This uses a default self-signed certificate.  Change the paths to
# use an alternative set of keys
ssl = False
if ssl:
    CherryPyWSGIServer.ssl_certificate = "./ssl/cacert.pem"
    CherryPyWSGIServer.ssl_private_key = "./ssl/privkey.pem"
            
# SWORD URLS
#############################################################################
# Define our URL mappings for the web service.  We are using URL parts immediately after the base of the service
# which reflect the short-hand terms used in the SWORD documentation (sd-uri, col-uri, cont-uri, em-uri and edit-uri
#
urls = (
    '/', 'WebUI',                               # Home page, with an intro and some handy links
    '/sd-uri', 'ServiceDocument',               # From which to retrieve the service document
    '/sd-uri/(.+)', 'ServiceDocument',          # for sub-service documents
    '/col-uri/(.+)', 'Collection',              # Representing a Collection as listed in the service document
    '/cont-uri/(.+)', 'MediaResourceContent',   # The URI used in atom:content@src
    '/em-uri/(.+)', 'MediaResource',            # The URI used in atom:link@rel=edit-media
    '/edit-uri/(.+)', 'Container',              # The URI used in atom:link@rel=edit
    '/state-uri/(.+)', 'StatementHandler',      # The URI used in atom:link@rel=sword:statement

    '/agg-uri/(.+)', 'Aggregation',              # The URI used to represent the ORE aggregation

    # NOT PART OF SWORD: sword says nothing about how components of the item are identified, but here we use the
    # PART-URI prefix to denote parts of the object in the server
    '/part-uri/(.+)', 'Part',

    # NOT PART OF SWORD: for convenience to supply HTML pages of deposited content
    '/html/(.+)', 'WebUI'
)

# USEFUL TERM MAPS
#############################################################################

HEADER_MAP = {
    HttpHeaders.in_progress : "HTTP_IN_PROGRESS",
    HttpHeaders.metadata_relevant : "HTTP_METADATA_RELEVANT",
    HttpHeaders.on_behalf_of : "HTTP_ON_BEHALF_OF"
}

STATUS_MAP = {
    400 : "400 Bad Request",
    401 : "401 Unauthorized",
    402 : "402 Payment Required",
    403 : "403 Forbidden",
    404 : "404 Not Found",
    405 : "405 Method Not Allowed",
    406 : "406 Not Acceptable",
    412 : "412 Precodition Failed",
    413 : "412 Request Entity Too Large",
    415 : "415 Unsupported Media Type"
}

# SWORD HTTP HANDLERS
#############################################################################
# Define a set of handlers for the various URLs defined above to be used by web.py

class SwordHttpHandler(object):
    def http_basic_authenticate(self, web):
        # extract the appropriate HTTP headers
        auth_header = web.ctx.env.get('HTTP_AUTHORIZATION')
        obo = web.ctx.env.get(HEADER_MAP[HttpHeaders.on_behalf_of])

        # if we're not supplied with an auth header, bounce
        if auth_header is None:
            ssslog.info("No auth header supplied; will return 401 with SSS realm")
            web.header('WWW-Authenticate','Basic realm="SSS"')
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
        
        ssslog.info("Authentication details: " + str(username) + ":[**password**]; On Behalf Of: " + str(obo))

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
        status = STATUS_MAP.get(sword_error.status, "400 Bad Request")
        ssslog.info("Returning error (" + str(sword_error.status) + ") - " + str(sword_error.error_uri))
        web.ctx.status = status
        if not sword_error.empty:
            web.header("Content-Type", "text/xml")
            return sword_error.error_document
        return
    
    def _map_webpy_headers(self, headers):
        return dict([(c[0][5:].replace("_", "-") if c[0].startswith("HTTP_") else c[0].replace("_", "-"), c[1]) for c in headers.items()])
    
    def validate_delete_request(self, web, section):
        h = HttpHeaders()
        
        # map the headers to standard http
        mapped_headers = self._map_webpy_headers(web.ctx.environ)
        ssslog.debug("Validating on header dictionary: " + str(mapped_headers))
        
        try:
            # now validate the http headers
            h.validate(mapped_headers, section)
        except ValidationError as e:
            raise SwordError(error_uri=Errors.bad_request, msg=e.message)
    
    def validate_deposit_request(self, web, entry_section=None, binary_section=None, multipart_section=None, empty_section=None, allow_multipart=True, allow_empty=False):
        h = HttpHeaders()

        # map the headers to standard http
        mapped_headers = self._map_webpy_headers(web.ctx.environ)
        ssslog.debug("Validating on header dictionary: " + str(mapped_headers))
  
        # run the validation
        try:
            # there must be both an "atom" and "payload" input or data in web.data()
            webin = web.input()
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
                if web.data() is None or web.data().strip() == "": # FIXME: this does not look safe to scale
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
                ssslog.info("Validating an atom-only deposit")
                is_entry = True
            
            if not is_entry and not is_multipart and not is_empty:
                ssslog.info("Validating a binary deposit")
            
            section = entry_section if is_entry else multipart_section if is_multipart else empty_section if is_empty else binary_section
            
            # now validate the http headers
            h.validate(mapped_headers, section)
            
        except ValidationException as e:
            raise SwordError(error_uri=Errors.bad_request, msg=e.message)
            
    def get_deposit(self, web, auth=None, atom_only=False):
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
        mapped_headers = self._map_webpy_headers(web.ctx.environ)
        
        # get the headers that have been provided.  Any headers which have not been provided will
        # will have default values applied
        h = HttpHeaders()
        d.set_from_headers(h.get_sword_headers(mapped_headers))
        
        if d.content_type.startswith("application/atom+xml"):
            atom_only=True
        
        empty_request = False
        if d.content_length == 0:
            ssslog.info("Received empty deposit request")
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
        webin = web.input()
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
                d.atom = web.data()
            else:
                ssslog.info("Received Binary deposit request")
                d.content = web.data()
        
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

class ServiceDocument(SwordHttpHandler):
    """
    Handle all requests for Service documents (requests to SD-URI)
    """
    def GET(self, sub_path=None):
        """ 
        GET the service document - returns an XML document 
        - sub_path - the path provided for the sub-service document
        """
        ssslog.debug("GET on Service Document (retrieve service document); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # authenticate
        try:
            auth = self.http_basic_authenticate(web)
        except SwordError as e:
            return self.manage_error(e)

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SwordServer(config, auth)
        sd = ss.service_document(sub_path)
        web.header("Content-Type", "text/xml")
        return sd

class Collection(SwordHttpHandler):
    """
    Handle all requests to SWORD/ATOM Collections (these are the collections listed in the Service Document) - Col-URI
    """
    def GET(self, collection):
        """
        GET a representation of the collection in XML
        Args:
        - collection:   The ID of the collection as specified in the requested URL
        Returns an XML document with some metadata about the collection and the contents of that collection
        """
        ssslog.debug("GET on Collection (list collection contents); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # authenticate
        try:
            auth = self.http_basic_authenticate(web)
        except SwordError as e:
            return self.manage_error(e)

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SwordServer(config, auth)
        cl = sss.list_collection(collection)
        web.header("Content-Type", "text/xml")
        return cl
        
    def POST(self, collection):
        """
        POST either an Atom Multipart request, or a simple package into the specified collection
        Args:
        - collection:   The ID of the collection as specified in the requested URL
        Returns a Deposit Receipt
        """
        ssslog.debug("POST to Collection (create new item); Incoming HTTP headers: " + str(web.ctx.environ))
        
        try:
            # authenticate
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request
            self.validate_deposit_request(web, "6.3.3", "6.3.1", "6.3.2")
        
            # take the HTTP request and extract a Deposit object from it    
            deposit = self.get_deposit(web, auth)
            
            # go ahead and process the deposit.  Anything other than a success
            # will be raised as a sword error
            ss = SwordServer(config, auth)
            result = ss.deposit_new(collection, deposit)
            
            # created
            ssslog.info("Item created")
            web.header("Content-Type", "application/atom+xml;type=entry")
            web.header("Location", result.location)
            web.ctx.status = "201 Created"
            if config.return_deposit_receipt:
                ssslog.info("Returning deposit receipt")
                return result.receipt
            else:
                ssslog.info("Omitting deposit receipt")
                return
            
        except SwordError as e:
            return self.manage_error(e)

class MediaResourceContent(SwordHttpHandler):
    """
    Class to represent the content of the media resource.  This is the object which appears under atom:content@src, not
    the EM-URI.  It has its own class handler because it is a distinct resource, which does not necessarily resolve to
    the same location as the EM-URI.  See the Atom and SWORD specs for more details.
    """
    def GET(self, path):
        """
        GET the media resource content in the requested format (web request will include content negotiation via
        Accept header)
        Args:
        - id:   the ID of the object in the store
        Returns the content in the requested format
        """
        ssslog.debug("GET on MediaResourceContent; Incoming HTTP headers: " + str(web.ctx.environ))
        
        # NOTE: this method is not authenticated - we imagine sharing this URL with end-users who will just want
        # to retrieve the content.  It's only for the purposes of example, anyway
        ss = SwordServer(config, None)

        # first thing we need to do is check that there is an object to return, because otherwise we may throw a
        # 406 Not Acceptable without looking first to see if there is even any media to content negotiate for
        # which would be weird from a client perspective
        if not ss.media_resource_exists(path):
            return web.notfound()
        
        # get the content negotiation headers
        accept_header = web.ctx.environ.get("HTTP_ACCEPT")
        accept_packaging_header = web.ctx.environ.get("HTTP_ACCEPT_PACKAGING")
        
        # do the negotiation
        default_accept_parameters, acceptable = config.get_media_resource_formats()
        cn = ContentNegotiator(default_accept_parameters, acceptable)
        accept_parameters = cn.negotiate(accept=accept_header, accept_packaging=accept_packaging_header)
        
        ssslog.info("Conneg format: " + str(accept_parameters))

        try:
            # can get hold of the media resource
            media_resource = ss.get_media_resource(path, accept_parameters)
        except SwordError as e:
            return self.manage_error(e)

        # either send the client a redirect, or stream the content out
        if media_resource.redirect:
            return web.found(media_resource.url)
        else:
            web.header("Content-Type", media_resource.content_type)
            if media_resource.packaging is not None:
                web.header("Packaging", media_resource.packaging)
            f = open(media_resource.filepath, "r")
            web.ctx.status = "200 OK"
            return f.read()

class MediaResource(MediaResourceContent):
    """
    Class to represent the media resource itself (EM-URI).  This extends from the MediaResourceContent class to take advantage
    of the GET method available there.  In a real implementation of AtomPub/SWORD the MediaResource and the
    MediaResourceContent are allowed to be separate entities, which can behave differently (see the specs for more
    details).  For the purposes of SSS, we are treating them the same for convenience.
    """
    def PUT(self, path):
        """
        PUT a new package onto the object identified by the supplied id
        Args:
        - id:   the ID of the media resource as specified in the URL
        Returns a Deposit Receipt
        """
        ssslog.debug("PUT on Media Resource (replace); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        if not config.allow_update:
            error = SwordError(error_uri=Errors.method_not_allowed, msg="Update operations not currently permitted")
            return self.manage_error(error)

        # authenticate
        try:
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request (note that multipart requests 
            # and atom-only are not permitted in this method)
            self.validate_deposit_request(web, None, "6.5.1", None, allow_multipart=False)
            
            # get a deposit object.  The PUT operation only supports a single binary deposit, not an Atom Multipart one
            # so if the deposit object has an atom part we should return an error
            deposit = self.get_deposit(web, auth)
            
            # now replace the content of the container
            ss = SwordServer(config, auth)
            result = ss.replace(path, deposit)
            
            # replaced
            ssslog.info("Content replaced")
            web.ctx.status = "204 No Content" # notice that this is different from the POST as per AtomPub
            return
            
        except SwordError as e:
            return self.manage_error(e)
        
    def DELETE(self, path):
        """
        DELETE the contents of an object in the store (but not the object's container), leaving behind an empty
        container for further use
        Args:
        - id:   the ID of the object to have its content removed as per the requested URI
        Return a Deposit Receipt
        """
        ssslog.debug("DELETE on Media Resource (remove content, leave container); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if delete is allowed
        if not config.allow_delete:
            error = SwordError(error_uri=Errors.method_not_allowed, msg="Delete operations not currently permitted")
            return self.manage_error(error)

        # authenticate
        try:
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request
            self.validate_delete_request(web, "6.6")
            
            # parse the delete request out of the HTTP request
            delete = self.get_delete(web, auth)
            
            # carry out the delete
            ss = SwordServer(config, auth)
            result = ss.delete_content(path, delete)
            
            # just return, no need to give any more feedback
            web.ctx.status = "204 No Content" # No Content
            return
            
        except SwordError as e:
            return self.manage_error(e)
    
    def POST(self, path):
        """
        POST a simple package into the specified media resource
        Args:
        - id:   The ID of the media resource as specified in the requested URL
        Returns a Deposit Receipt
        """
        ssslog.debug("POST to Media Resource (add new file); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        if not config.allow_update:
            error = SwordError(error_uri=Errors.method_not_allowed, msg="Update operations not currently permitted")
            return self.manage_error(error)
            
        # authenticate
        try:
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request
            self.validate_deposit_request(web, None, "6.7.1", None, allow_multipart=False)
            
            deposit = self.get_deposit(web, auth)
            
            # if we get here authentication was successful and we carry on
            ss = SwordServer(config, auth)
            result = ss.add_content(path, deposit)
            
            web.header("Content-Type", "application/atom+xml;type=entry")
            web.header("Location", result.location)
            web.ctx.status = "201 Created"
            if config.return_deposit_receipt:
                return result.receipt
            else:
                return
            
        except SwordError as e:
            return self.manage_error(e)

class Container(SwordHttpHandler):
    """
    Class to deal with requests to the container, which is represented by the main Atom Entry document returned in
    the deposit receipt (Edit-URI).
    """
    def GET(self, path):
        """
        GET a representation of the container in the appropriate (content negotiated) format as identified by
        the supplied id
        Args:
        - id:   The ID of the container as supplied in the request URL
        Returns a representation of the container: SSS will return either the Atom Entry identical to the one supplied
        as a deposit receipt or the pure RDF/XML Statement depending on the Accept header
        """
        ssslog.debug("GET on Container (retrieve deposit receipt or statement); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # authenticate
        try:
            auth = self.http_basic_authenticate(web)
            
            ss = SwordServer(config, auth)
            
            # first thing we need to do is check that there is an object to return, because otherwise we may throw a
            # 415 Unsupported Media Type without looking first to see if there is even any media to content negotiate for
            # which would be weird from a client perspective
            if not ss.container_exists(path):
                return web.notfound()
                
            # get the content negotiation headers
            accept_header = web.ctx.environ.get("HTTP_ACCEPT")
            accept_packaging_header = web.ctx.environ.get("HTTP_ACCEPT_PACKAGING")
            
            # do the negotiation
            default_accept_parameters, acceptable = config.get_container_formats()
            cn = ContentNegotiator(default_accept_parameters, acceptable)
            accept_parameters = cn.negotiate(accept=accept_header)
            ssslog.info("Container requested in format: " + str(accept_parameters))
            
            # did we successfully negotiate a content type?
            if accept_parameters is None:
                raise SwordError(error_uri=Error.content, status=415, empty=True)
            
            # now actually get hold of the representation of the container and send it to the client
            cont = ss.get_container(path, accept_parameters)
            return cont
            
        except SwordError as e:
            return self.manage_error(e)

    def PUT(self, path):
        """
        PUT a new Entry over the existing entry, or a multipart request over
        both the existing metadata and the existing content
        """
        ssslog.debug("PUT on Container (replace); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        if not config.allow_update:
            error = SwordError(error_uri=Errors.method_not_allowed, msg="Update operations not currently permitted")
            return self.manage_error(error)
        
        try:
            # authenticate
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request
            self.validate_deposit_request(web, "6.5.2", None, "6.5.3")
            
            # get the deposit object
            deposit = self.get_deposit(web, auth)
            
            ss = SwordServer(config, auth)
            result = ss.replace(path, deposit)
            
            web.header("Location", result.location)
            if config.return_deposit_receipt:
                web.header("Content-Type", "application/atom+xml;type=entry")
                web.ctx.status = "200 OK"
                return result.receipt
            else:
                web.ctx.status = "204 No Content"
                return
                
        except SwordError as e:
            return self.manage_error(e)
    
    # NOTE: this POST action on the Container is represented in the specification
    # by a POST to the SE-IRI (The SWORD Edit IRI), sections 6.7.2 and 6.7.3 and
    # also to support completing unfinished deposits as per section 9.3
    def POST(self, path):
        """
        POST some new content into the container identified by the supplied id,
        or complete an existing deposit (using the In-Progress header)
        Args:
        - id:    The ID of the container as contained in the URL
        Returns a Deposit Receipt
        """
        ssslog.debug("POST to Container (add new content and metadata); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        if not config.allow_update:
            error = SwordError(error_uri=Errors.method_not_allowed, msg="Update operations not currently permitted")
            return self.manage_error(error)

        try:
             # authenticate
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request
            self.validate_deposit_request(web, "6.7.2", None, "6.7.3", "9.3", allow_empty=True)
            
            deposit = self.get_deposit(web, auth)
            
            ss = SwordServer(config, auth)
            result = ss.deposit_existing(path, deposit)
            
            # NOTE: spec says 201 Created for multipart and 200 Ok for metadata only
            # we have implemented 200 OK across the board, in the understanding that
            # in this case the spec is incorrect (correction need to be implemented
            # asap)
            
            web.header("Location", result.location)
            web.ctx.status = "200 OK"
            if config.return_deposit_receipt:
                web.header("Content-Type", "application/atom+xml;type=entry")
                return result.receipt
            else:
                return
            
        except SwordError as e:
            return self.manage_error(e)

    def DELETE(self, path):
        """
        DELETE the container (and everything in it) from the store, as identified by the supplied id
        Args:
        - id:   the ID of the container
        Returns nothing, as there is nothing to return (204 No Content)
        """
        ssslog.debug("DELETE on Container (remove); Incoming HTTP headers: " + str(web.ctx.environ))
        
        try:
            # find out if update is allowed
            if not config.allow_delete:
                raise SwordError(error_uri=Errors.method_not_allowed, msg="Delete operations not currently permitted")
            
            # authenticate
            auth = self.http_basic_authenticate(web)
            
            # check the validity of the request
            self.validate_delete_request(web, "6.8")
            
            # get the delete request
            delete = self.get_delete(web, auth)
           
            # do the delete
            ss = SwordServer(config, auth)
            result = ss.delete_container(path, delete)
            
            # no need to return any content
            web.ctx.status = "204 No Content"
            return
            
        except SwordError as e:
            return self.manage_error(e)

class StatementHandler(SwordHttpHandler):
    def GET(self, path):
        ssslog.debug("GET on Statement (retrieve); Incoming HTTP headers: " + str(web.ctx.environ))
        
        try:
            # authenticate
            auth = self.http_basic_authenticate(web)
            
            ss = SwordServer(config, auth)
            
            # first thing we need to do is check that there is an object to return, because otherwise we may throw a
            # 415 Unsupported Media Type without looking first to see if there is even any media to content negotiate for
            # which would be weird from a client perspective
            if not ss.container_exists(path):
                raise SwordError(status=404, empty=True)
            
            # now actually get hold of the representation of the statement and send it to the client
            cont = ss.get_statement(path)
            return cont
            
        except SwordError as e:
            return self.manage_error(e)
            

# OTHER HTTP HANDLERS
#############################################################################
# Define a set of handlers for the various URLs defined above to be used by web.py
# These ones aren't anything to do with the SWORD standard, they are just 
# convenient to support the additional URIs produced          

class Aggregation(SwordHttpHandler):
    def GET(self, path):
        # in this case we just redirect back to the Edit-URI with a 303 See Other
        ss = SwordServer(config, None)
        edit_uri = ss.get_edit_uri()
        web.ctx.status = "303 See Other"
        web.header("Content-Location", edit_uri)
        return

class WebUI(SwordHttpHandler):
    """
    Class to provide a basic web interface to the store for convenience
    """
    def GET(self, path=None):
        if path is not None:
            if path.find("/") >= 0:
                ip = ItemPage(config)
                return ip.get_item_page(path)
            else:
                cp = CollectionPage(config)
                return cp.get_collection_page(path)
        else:
            hp = HomePage(config)
            return hp.get_home_page()

class Part(SwordHttpHandler):
    """
    Class to provide access to the component parts of the object on the server
    """
    def GET(self, path):
        ss = SwordServer(config, None)
        
        # if we did, we can get hold of the media resource
        fh = ss.get_part(path)
        
        if fh is None:
            return web.notfound()

        web.header("Content-Type", "application/octet-stream") # we're not keeping track of content types
        web.ctx.status = "200 OK"
        return fh.read()
        
    def PUT(self, path):
        # FIXME: the spec says that we should either support this or return
        # 405 Method Not Allowed.
        # This would be useful for DepositMO compliance, so we should consider
        # implementing this when time permits
        web.ctx.status = "405 Method Not Allowed"
        return
        
                
# WEB SERVER
#######################################################################
# This is the bit which actually invokes the web.py server when this module is run

# if we run the file as a mod_wsgi module, do this
application = web.application(urls, globals()).wsgifunc()

# if we run the file directly, use the bundled CherryPy server ...
if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()
