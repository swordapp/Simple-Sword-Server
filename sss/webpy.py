import web, re, base64, urllib, uuid
from web.wsgiserver import CherryPyWSGIServer
from config import CherryPyConfiguration
from core import Auth, SWORDSpec
from repository import SWORDServer
from negotiator import ContentNegotiator, ContentType
from webui import HomePage, CollectionPage, ItemPage

from sss_logging import logging
ssslog = logging.getLogger(__name__)

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


# HTTP HANDLERS
#############################################################################
# Define a set of handlers for the various URLs defined above to be used by web.py

class SwordHttpHandler(object):
    def authenticate(self, web):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        obo = web.ctx.env.get("HTTP_ON_BEHALF_OF")

        cfg = global_configuration

        # we may have turned authentication off for development purposes
        if not cfg.authenticate:
            ssslog.info("Authentication is turned OFF")
            return Auth(cfg.user)
        else:
            ssslog.info("Authentication required")

        # if we want to authenticate, but there is no auth string then bounce with a 401 (realm SSS)
        if auth is None:
            ssslog.info("No authentication credentials supplied, requesting authentication")
            web.header('WWW-Authenticate','Basic realm="SSS"')
            web.ctx.status = '401 Unauthorized'
            return Auth()
        else:
            # assuming Basic authentication, get the username and password
            auth = re.sub('^Basic ','',auth)
            username, password = base64.decodestring(auth).split(':')
            ssslog.info("Authentication details: " + str(username) + ":" + str(password) + "; On Behalf Of: " + str(obo))

            # if the username and password don't match, bounce the user with a 401
            # meanwhile if the obo header has been passed but doesn't match the config value also bounce
            # witha 401 (I know this is an odd looking if/else but it's for clarity of what's going on
            if username != cfg.user or password != cfg.password:
                ssslog.info("Authentication Failed; returning 401")
                web.ctx.status = '401 Unauthorized'
                return Auth()
            elif obo is not None and obo != cfg.obo:
                ssslog.info("Authentication Failed with Target Owner Unknown")
                # we throw a sword error for TargetOwnerUnknown
                return Auth(cfg.user, obo, target_owner_unknown=True)

        user = cfg.user
        if obo is not None:
            return Auth(user, obo)
        return Auth(user)

class ServiceDocument(SwordHttpHandler):
    """
    Handle all requests for Service documents (requests to SD-URI)
    """
    def GET(self, sub=None):
        """ GET the service document - returns an XML document """
        ssslog.debug("GET on Service Document; Incoming HTTP headers: " + str(web.ctx.environ))
        
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer(URIManager())
        web.header("Content-Type", "text/xml")
        use_sub = global_configuration.use_sub if sub is None else False
        return ss.service_document(use_sub)

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
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer(URIManager())
        web.header("Content-Type", "text/xml")
        return ss.list_collection(collection)
        
    def POST(self, collection):
        """
        POST either an Atom Multipart request, or a simple package into the specified collection
        Args:
        - collection:   The ID of the collection as specified in the requested URL
        Returns a Deposit Receipt
        """
        ssslog.debug("POST to Collection (create new item); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request
        invalid = spec.validate_deposit_request(web)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        # take the HTTP request and extract a Deposit object from it
        deposit = spec.get_deposit(web, auth)
        if deposit.too_large:
            error = ss.sword_error(spec.error_max_upload_size_exceeded, "Your deposit exceeds the maximum upload size limit")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "413 Request Entity Too Large"
            return error
        result = ss.deposit_new(collection, deposit)

        if result is None:
            return web.notfound()

        cfg = global_configuration

        # created, accepted, or error
        if result.created:
            print cfg.rid + " Item created"
            web.header("Content-Type", "application/atom+xml;type=entry")
            web.header("Location", result.location)
            web.ctx.status = "201 Created"
            if cfg.return_deposit_receipt:
                print cfg.rid + " Returning deposit receipt"
                return result.receipt
            else:
                print cfg.rid + " Omitting deposit receipt"
                return
        else:
            print cfg.rid + " Returning Error"
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error

class MediaResourceContent(SwordHttpHandler):
    """
    Class to represent the content of the media resource.  This is the object which appears under atom:content@src, not
    the EM-URI.  It has its own class handler because it is a distinct resource, which does not necessarily resolve to
    the same location as the EM-URI.  See the Atom and SWORD specs for more details.
    """
    def GET(self, id):
        """
        GET the media resource content in the requested format (web request will include content negotiation via
        Accept header)
        Args:
        - id:   the ID of the object in the store
        Returns the content in the requested format
        """
        
        ssslog.debug("GET on MediaResourceContent; Incoming HTTP headers: " + str(web.ctx.environ))
        
        # check to see if we're after the .atom version of the content
        atom = False
        if id.endswith(".atom"):
            id = id[:-5]
            atom = True
        
        # NOTE: this method is not authenticated - we imagine sharing this URL with end-users who will just want
        # to retrieve the content.  It's only for the purposes of example, anyway
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # first thing we need to do is check that there is an object to return, because otherwise we may throw a
        # 415 Unsupported Media Type without looking first to see if there is even any media to content negotiate for
        # which would be weird from a client perspective
        if not ss.exists(id):
            return web.notfound()
        
        content_type = None
        if not atom:
            # do some content negotiation
            cn = ContentNegotiator()

            # if no Accept header, then we will get this back
            cn.default_type = "application"
            cn.default_subtype = "zip"
            cn.default_packaging = None

            # The list of acceptable formats (in order of preference).
            # FIXME: ultimately to replace this with the negotiator
            cn.acceptable = [
                    ContentType("application", "zip", None, "http://purl.org/net/sword/package/SimpleZip"),
                    ContentType("application", "zip"),
                    ContentType("application", "atom+xml", "type=feed"),
                    ContentType("text", "html")
                ]

            # do the negotiation
            content_type = cn.negotiate(web.ctx.environ)
        else:
            content_type = ContentType("application", "atom+xml", "type=feed")

        # did we successfully negotiate a content type?
        if content_type is None:
            error = ss.sword_error(spec.error_content_uri, "Requsted Accept-Packaging is not supported by this server")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "406 Not Acceptable"
            return error
        
        # if we did, we can get hold of the media resource
        media_resource = ss.get_media_resource(id, content_type)

        # either send the client a redirect, or stream the content out
        if media_resource.redirect:
            return web.found(media_resource.url)
        else:
            web.header("Content-Type", content_type.mimetype())
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
    def PUT(self, id):
        """
        PUT a new package onto the object identified by the supplied id
        Args:
        - id:   the ID of the media resource as specified in the URL
        Returns a Deposit Receipt
        """
        ssslog.debug("PUT on Media Resource (replace); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        cfg = global_configuration
        if not cfg.allow_update:
            spec = SWORDSpec()
            ss = SWORDServer(URIManager())
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request (note that multipart requests are not permitted in this method)
        invalid = spec.validate_deposit_request(web, allow_multipart=False)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        # next, before processing the request, let's check that the id is valid, and if not 404 the client
        if not ss.exists(id):
            return web.notfound()

        # get a deposit object.  The PUT operation only supports a single binary deposit, not an Atom Multipart one
        # so if the deposit object has an atom part we should return an error
        deposit = spec.get_deposit(web, auth)
        if deposit.too_large:
            error = ss.sword_error(spec.error_max_upload_size_exceeded, "Your deposit exceeds the maximum upload size limit")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "413 Request Entity Too Large"
            return error
        
        # now replace the content of the container
        result = ss.replace(id, deposit)

        # created, accepted or error
        if result.created:
            ssslog.info("Content replaced")
            web.ctx.status = "204 No Content" # notice that this is different from the POST as per AtomPub
            return
        else:
            ssslog.info("Returning Error")
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error

    def DELETE(self, id):
        """
        DELETE the contents of an object in the store (but not the object's container), leaving behind an empty
        container for further use
        Args:
        - id:   the ID of the object to have its content removed as per the requested URI
        Return a Deposit Receipt
        """
        ssslog.debug("DELETE on Media Resource (remove content, leave container); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if delete is allowed
        cfg = global_configuration
        if not cfg.allow_delete:
            spec = SWORDSpec()
            ss = SWORDServer(URIManager())
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Delete operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request
        invalid = spec.validate_delete_request(web)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        # parse the delete request out of the HTTP request
        delete = spec.get_delete(web.ctx.environ, auth)

        # next, before processing the request, let's check that the id is valid, and if not 404 the client
        if not ss.exists(id):
            return web.notfound()

        # carry out the delete
        result = ss.delete_content(id, delete)

        # if there was an error, report it, otherwise return the deposit receipt
        if result.error_code is not None:
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error
        else:
            web.ctx.status = "204 No Content" # No Content
            return
    
    def POST(self, id):
        """
        POST a simple package into the specified media resource
        Args:
        - id:   The ID of the media resource as specified in the requested URL
        Returns a Deposit Receipt
        """
        ssslog.debug("POST to Media Resource (add new file); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        cfg = global_configuration
        if not cfg.allow_update:
            spec = SWORDSpec()
            ss = SWORDServer(URIManager())
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error
            
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request
        invalid = spec.validate_deposit_request(web)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        # next, before processing the request, let's check that the id is valid, and if not 404 the client
        if not ss.exists(id):
            return web.notfound()

        # take the HTTP request and extract a Deposit object from it
        deposit = spec.get_deposit(web, auth)
        if deposit.too_large:
            error = ss.sword_error(spec.error_max_upload_size_exceeded, "Your deposit exceeds the maximum upload size limit")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "413 Request Entity Too Large"
            return error
                
        result = ss.add_content(id, deposit)

        if result is None:
            return web.notfound()

        cfg = global_configuration

        # created, accepted, or error
        if result.created:
            web.header("Content-Type", "application/atom+xml;type=entry")
            web.header("Location", result.location)
            web.ctx.status = "201 Created"
            if cfg.return_deposit_receipt:
                return result.receipt
            else:
                return
        else:
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error

class Container(SwordHttpHandler):
    """
    Class to deal with requests to the container, which is represented by the main Atom Entry document returned in
    the deposit receipt (Edit-URI).
    """
    def GET(self, id):
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
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer(URIManager())

        # first thing we need to do is check that there is an object to return, because otherwise we may throw a
        # 415 Unsupported Media Type without looking first to see if there is even any media to content negotiate for
        # which would be weird from a client perspective
        if not ss.exists(id):
            return web.notfound()

        # do some content negotiation
        cn = ContentNegotiator()

        # if no Accept header, then we will get this back
        cn.default_type = "application"
        cn.default_subtype = "atom+xml"
        cn.default_params = "type=entry"
        cn.default_packaging = None

        # The list of acceptable formats (in order of preference).  The tuples list the type and
        # the parameters section respectively
        cn.acceptable = [
                ContentType("application", "atom+xml", "type=entry"),
                ContentType("application", "atom+xml", "type=feed"),
                ContentType("application", "rdf+xml")
            ]

        # do the negotiation
        content_type = cn.negotiate(web.ctx.environ)

        # did we successfully negotiate a content type?
        if content_type is None:
            web.ctx.status = "415 Unsupported Media Type"
            return

        # now actually get hold of the representation of the container and send it to the client
        cont = ss.get_container(id, content_type)
        return cont

    def PUT(self, id):
        """
        PUT a new Entry over the existing entry, or a multipart request over
        both the existing metadata and the existing content
        """
        ssslog.debug("PUT on Container (replace); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        cfg = global_configuration
        if not cfg.allow_update:
            spec = SWORDSpec()
            ss = SWORDServer(URIManager())
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error
        
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request
        invalid = spec.validate_deposit_request(web)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        # take the HTTP request and extract a Deposit object from it
        deposit = spec.get_deposit(web, auth)
        if deposit.too_large:
            error = ss.sword_error(spec.error_max_upload_size_exceeded, "Your deposit exceeds the maximum upload size limit")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "413 Request Entity Too Large"
            return error
        result = ss.replace(id, deposit)

        # FIXME: this is no longer relevant
        # take the HTTP request and extract a Deposit object from it
        #deposit = spec.get_deposit(web, auth, atom_only=True)
        #result = ss.update_metadata(id, deposit)

        if result is None:
            return web.notfound()

        # created, accepted, or error
        if result.created:
            web.header("Location", result.location)
            if cfg.return_deposit_receipt:
                web.header("Content-Type", "application/atom+xml;type=entry")
                web.ctx.status = "200 OK"
                return result.receipt
            else:
                web.ctx.status = "204 No Content"
                return
        else:
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error

    # NOTE: this POST action on the Container is represented in the specification
    # by a POST to the SE-IRI (The SWORD Edit IRI), sections 6.7.2 and 6.7.3 and
    # also to support completing unfinished deposits as per section 9.3
    def POST(self, id):
        """
        POST some new content into the container identified by the supplied id,
        or complete an existing deposit (using the In-Progress header)
        Args:
        - id:    The ID of the container as contained in the URL
        Returns a Deposit Receipt
        """
        ssslog.debug("POST to Container (add new content and metadata); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        cfg = global_configuration
        if not cfg.allow_update:
            spec = SWORDSpec()
            ss = SWORDServer(URIManager())
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request
        invalid = spec.validate_deposit_request(web)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        # take the HTTP request and extract a Deposit object from it
        deposit = spec.get_deposit(web, auth)
        if deposit.too_large:
            error = ss.sword_error(spec.error_max_upload_size_exceeded, "Your deposit exceeds the maximum upload size limit")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "413 Request Entity Too Large"
            return error
        result = ss.deposit_existing(id, deposit)

        if result is None:
            # we couldn't find the id
            return web.notfound()
        
        # NOTE: spec says 201 Created for multipart and 200 Ok for metadata only
        # we have implemented 200 OK across the board, in the understanding that
        # in this case the spec is incorrect (correction need to be implemented
        # asap)
        
        # created, accepted or error
        if result.created:
            web.header("Location", result.location)
            web.ctx.status = "200 OK"
            if cfg.return_deposit_receipt:
                web.header("Content-Type", "application/atom+xml;type=entry")
                return result.receipt
            else:
                return
        else:
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error

    def DELETE(self, id):
        """
        DELETE the container (and everything in it) from the store, as identified by the supplied id
        Args:
        - id:   the ID of the container
        Returns nothing, as there is nothing to return (204 No Content)
        """
        ssslog.debug("DELETE on Container (remove); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # find out if update is allowed
        cfg = global_configuration
        if not cfg.allow_delete:
            spec = SWORDSpec()
            ss = SWORDServer(URIManager())
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Delete operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer(URIManager())
        spec = SWORDSpec()

        # check the validity of the request
        invalid = spec.validate_delete_request(web)
        if invalid is not None:
            error = ss.sword_error(spec.error_bad_request_uri, invalid)
            web.header("Content-Type", "text/xml")
            web.ctx.status = "400 Bad Request"
            return error

        delete = spec.get_delete(web.ctx.environ, auth)

        # next, before processing the request, let's check that the id is valid, and if not 404 the client
        if not ss.exists(id):
            return web.notfound()

        # carry out the delete
        result = ss.delete_container(id, delete)

        # if there was an error, report it, otherwise return the deposit receipt
        if result.error_code is not None:
            web.header("Content-Type", "text/xml")
            web.ctx.status = result.error_code
            return result.error
        else:
            web.ctx.status = "204 No Content"
            return

class StatementHandler(SwordHttpHandler):
    def GET(self, id):
        ssslog.debug("GET on Statement (retrieve); Incoming HTTP headers: " + str(web.ctx.environ))
        
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer(URIManager())
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer(URIManager())

        # the get request will contain a suffix which is "rdf" or "atom" depending on
        # the desired return type
        content_type = None
        if id.endswith("rdf"):
            content_type = "application/rdf+xml"
            id = id[:-4]
        elif id.endswith("atom"):
            content_type = "application/atom+xml;type=feed"
            id = id[:-5]

        # first thing we need to do is check that there is an object to return, because otherwise we may throw a
        # 415 Unsupported Media Type without looking first to see if there is even any media to content negotiate for
        # which would be weird from a client perspective
        if not ss.exists(id):
            return web.notfound()

        # did we successfully negotiate a content type?
        if content_type is None:
            return web.notfound()

        # now actually get hold of the representation of the statement and send it to the client
        cont = ss.get_statement(id, content_type)
        return cont

class Aggregation(SwordHttpHandler):
    def GET(self, id):
        # in this case we just redirect back to the Edit-URI with a 303 See Other
        um = URIManager()
        col, oid = um.interpret_oid(id)
        edit_uri = um.edit_uri(col, oid)
        web.ctx.status = "303 See Other"
        web.header("Content-Location", edit_uri)
        return

class WebUI(SwordHttpHandler):
    """
    Class to provide a basic web interface to the store for convenience
    """
    def GET(self, id=None):
        if id is not None:
            if id.find("/") >= 0:
                ip = ItemPage(URIManager())
                return ip.get_item_page(id)
            else:
                cp = CollectionPage(URIManager())
                return cp.get_collection_page(id)
        else:
            hp = HomePage(URIManager())
            return hp.get_home_page()

class Part(SwordHttpHandler):
    """
    Class to provide access to the component parts of the object on the server
    """
    def GET(self, path):
        ss = SWORDServer(URIManager())
        
        # if we did, we can get hold of the media resource
        fh = ss.get_part(path)
        
        if fh is None:
            return web.notfound()

        web.header("Content-Type", "application/octet-stream") # we're not keeping track of content types
        web.ctx.status = "200 OK"
        return fh.read()
        
    def PUT(self, id):
        # FIXME: the spec says that we should either support this or return
        # 405 Method Not Allowed.
        # This would be useful for DepositMO compliance, so we should consider
        # implementing this when time permits
        web.ctx.status = "405 Method Not Allowed"
        return
        
        
class URIManager(object):
    """
    Class for providing a single point of access to all identifiers used by SSS
    """
    def __init__(self):
        self.configuration = global_configuration

    def html_url(self, collection, id=None):
        """ The url for the HTML splash page of an object in the store """
        if id is not None:
            return self.configuration.base_url + "html/" + collection + "/" + id
        return self.configuration.base_url + "html/" + collection

    def sd_uri(self, sub=True):
        uri = self.configuration.base_url + "sd-uri"
        if sub:
            uri += "/" + str(uuid.uuid4())
        return uri

    def col_uri(self, id):
        """ The url for a collection on the server """
        return self.configuration.base_url + "col-uri/" + id

    def edit_uri(self, collection, id):
        """ The Edit-URI """
        return self.configuration.base_url + "edit-uri/" + collection + "/" + id

    def em_uri(self, collection, id):
        """ The EM-URI """
        return self.configuration.base_url + "em-uri/" + collection + "/" + id

    def cont_uri(self, collection, id):
        """ The Cont-URI """
        return self.configuration.base_url + "cont-uri/" + collection + "/" + id

    def state_uri(self, collection, id, type):
        root = self.configuration.base_url + "state-uri/" + collection + "/" + id
        if type == "atom":
            return root + ".atom"
        elif type == "ore":
            return root + ".rdf"

    def part_uri(self, collection, id, filename):
        """ The URL for accessing the parts of an object in the store """
        return self.configuration.base_url + "part-uri/" + collection + "/" + id + "/" + urllib.quote(filename)

    def agg_uri(self, collection, id):
        return self.configuration.base_url + "agg-uri/" + collection + "/" + id

    def atom_id(self, collection, id):
        """ An ID to use for Atom Entries """
        return "tag:container@sss/" + collection + "/" + id

    def interpret_oid(self, oid):
        """
        Take an object id from a URL and interpret the collection and id terms.
        Returns a tuple of (collection, id)
        """
        collection, id = oid.split("/", 1)
        return collection, id
        
    def interpret_path(self, path):
        """
        Take a file path from a URL and interpret the collection, id and filename terms.
        Returns a tuple of (collection, id, filename)
        """
        collection, id, fn = path.split("/", 2)
        return collection, id, fn
        
# WEB SERVER
#######################################################################
# This is the bit which actually invokes the web.py server when this module is run

# FIXME: we need to sort out our approach to configuration first

# create the global configuration
global_configuration = CherryPyConfiguration()

# if we run the file as a mod_wsgi module, do this
application = web.application(urls, globals()).wsgifunc()

# if we run the file directly, use the bundled CherryPy server ...
if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()
