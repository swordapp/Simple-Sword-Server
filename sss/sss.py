""" SSS - Simple SWORD Server """

__version__ = "2.0"
__author__ = ["Richard Jones <richard@cottagelabs.com>"]
__license__ = "bsd"

import web, uuid, os, re, base64, hashlib, urllib, sys, logging, logging.config
from lxml import etree
from datetime import datetime
from zipfile import ZipFile
from web.wsgiserver import CherryPyWSGIServer

# SERVER CONFIGURATION
#############################################################################
# Use this class to specify all the bits of configuration that will be used
# in the sword server

# Whether to run using SSL.  This uses a default self-signed certificate.  Change the paths to
# use an alternative set of keys
ssl = False
if ssl:
    CherryPyWSGIServer.ssl_certificate = "./ssl/cacert.pem"
    CherryPyWSGIServer.ssl_private_key = "./ssl/privkey.pem"

class SSSLogger(object):
    def __init__(self):
        self.logging_config = "./sss_logging.conf"  # default
        self.basic_config = """[loggers]
keys=root

[handlers]
keys=consoleHandler

[formatters]
keys=basicFormatting

[logger_root]
level=INFO
handlers=consoleHandler

[handler_consoleHandler]
class=StreamHandler
level=DEBUG
formatter=basicFormatting
args=(sys.stdout,)

[formatter_basicFormatting]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s
"""

        if not os.path.isfile(self.logging_config):
            self.create_logging_config(self.logging_config)

        logging.config.fileConfig(self.logging_config)

    def create_logging_config(self, pathtologgingconf):
        fn = open(pathtologgingconf, "w")
        fn.write(self.basic_config)
        fn.close()
        
    def getLogger(self):
        return logging.getLogger(__name__)
        
class Configuration(object):
    def __init__(self):
        # The base url of the webservice where SSS is deployed
        self.base_url = "http://localhost:%s/" % (sys.argv[1] if len(sys.argv) > 1 else '8080')

        # The number of collections that SSS will create and give to users to deposit content into
        self.num_collections = 10

        # The directory where the deposited content should be stored
        self.store_dir = os.path.join(os.getcwd(), "store")

        # explicitly set the sword version, so if you're testing validation of
        # service documents you can "break" it.
        self.sword_version = "2.0" # SWORD 2.0!  Oh yes!
    
        # user details; the user/password pair should be used for HTTP Basic Authentication, and the obo is the user
        # to use for On-Behalf-Of requests.  Set authenticate=False if you want to test the server without caring
        # about authentication, set mediation=False if you want to test the server's errors on invalid attempts at
        # mediation
        self.authenticate = True
        self.user = "sword"
        self.password = "sword"
        
        self.mediation = True
        self.obo = "obo"

        # What media ranges should the app:accept element in the Service Document support
        self.app_accept = ["*/*"]
        self.multipart_accept = ["*/*"]
        self.accept_nothing = False
        
        # use these app_accept and multipart_accept values to create an invalid Service Document
        #self.app_accept = None
        #self.multipart_accept = None

        # should we provide sub-service urls
        self.use_sub = True

        # What packaging formats should the sword:acceptPackaging element in the Service Document support
        self.sword_accept_package = [
                "http://purl.org/net/sword/package/SimpleZip",
                "http://purl.org/net/sword/package/Binary",
                "http://purl.org/net/sword/package/METSDSpaceSIP"
            ]

        # maximum upload size to be allowed, in bytes (this default is 16Mb)
        self.max_upload_size = 16777216
        #self.max_upload_size = 0 # used to generate errors
        
        # list of package formats that SSS can provide when retrieving the Media Resource
        self.sword_disseminate_package = [
            "http://purl.org/net/sword/package/SimpleZip"
        ]

        # Supported package format disseminators; for the content type (dictionary key), the associated
        # class will be used to package the content for dissemination
        self.package_disseminators = {
                ContentType("application", "zip", None, "http://purl.org/net/sword/package/SimpleZip").media_format() : DefaultDisseminator,
                ContentType("application", "zip").media_format() : DefaultDisseminator,
                ContentType("application", "atom+xml", "type=feed").media_format() : FeedDisseminator
            }

        # Supported package format ingesters; for the Packaging header (dictionary key), the associated class will
        # be used to unpackage deposited content
        self.package_ingesters = {
                "http://purl.org/net/sword/package/Binary" : BinaryIngester,
                "http://purl.org/net/sword/package/SimpleZip" : SimpleZipIngester,
                "http://purl.org/net/sword/package/METSDSpaceSIP" : METSDSpaceIngester
            }
            
        self.entry_ingester = DefaultEntryIngester

        # supply this header in the Packaging header to generate a http://purl.org/net/sword/error/ErrorContent
        # sword error
        self.error_content_package = "http://purl.org/net/sword/package/error"

        # we can turn off updates and deletes in order to examine the behaviour of Method Not Allowed errors
        self.allow_update = True
        self.allow_delete = True

        # we can turn off deposit receipts, which is allowed by the specification
        self.return_deposit_receipt = True
        
        # generate a UUID to represent this request, for logging purposes
        self.rid = str(uuid.uuid4())

class CherryPyConfiguration(Configuration):
    def __init__(self):
        Configuration.__init__(self)

class ApacheConfiguration(Configuration):
    def __init__(self):
        Configuration.__init__(self)
        self.base_url = 'http://localhost/sss/'
        self.store_dir = '/Users/richard/tmp/store'
        self.authenticate = False

class Namespaces(object):
    """
    This class encapsulates all the namespace declarations that we will need
    """
    def __init__(self):
        # AtomPub namespace and lxml format
        self.APP_NS = "http://www.w3.org/2007/app"
        self.APP = "{%s}" % self.APP_NS

        # Atom namespace and lxml format
        self.ATOM_NS = "http://www.w3.org/2005/Atom"
        self.ATOM = "{%s}" % self.ATOM_NS

        # SWORD namespace and lxml format
        self.SWORD_NS = "http://purl.org/net/sword/terms/"
        self.SWORD = "{%s}" % self.SWORD_NS

        # Dublin Core namespace and lxml format
        self.DC_NS = "http://purl.org/dc/terms/"
        self.DC = "{%s}" % self.DC_NS

        # RDF namespace and lxml format
        self.RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        self.RDF = "{%s}" % self.RDF_NS

        # ORE namespace and lxml format
        self.ORE_NS = "http://www.openarchives.org/ore/terms/"
        self.ORE = "{%s}" % self.ORE_NS

        # ORE ATOM
        self.ORE_ATOM_NS = "http://www.openarchives.org/ore/atom/"
        self.ORE_ATOM = "{%s}" % self.ORE_ATOM_NS

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
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer()
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
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer()
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
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
        ss = SWORDServer()
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
            ss = SWORDServer()
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
            ss = SWORDServer()
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Delete operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
            ss = SWORDServer()
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error
            
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer()

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
            ss = SWORDServer()
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error
        
        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
            ss = SWORDServer()
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Update operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
            ss = SWORDServer()
            error = ss.sword_error(spec.error_method_not_allowed_uri, "Delete operations not currently permitted")
            web.header("Content-Type", "text/xml")
            web.ctx.status = "405 Method Not Allowed"
            return error

        # authenticate
        auth = self.authenticate(web)
        if not auth.success():
            if auth.target_owner_unknown:
                spec = SWORDSpec()
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on
        ss = SWORDServer()
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
                ss = SWORDServer()
                error = ss.sword_error(spec.error_target_owner_unknown_uri, auth.obo)
                web.header("Content-Type", "text/xml")
                web.ctx.status = "403 Forbidden"
                return error
            return

        # if we get here authentication was successful and we carry on (we don't care who authenticated)
        ss = SWORDServer()

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
                ip = ItemPage()
                return ip.get_item_page(id)
            else:
                cp = CollectionPage()
                return cp.get_collection_page(id)
        else:
            hp = HomePage()
            return hp.get_home_page()

class Part(SwordHttpHandler):
    """
    Class to provide access to the component parts of the object on the server
    """
    def GET(self, path):
        ss = SWORDServer()
        
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


# CONTENT NEGOTIATION
#######################################################################
# A sort of generic tool for carrying out content negotiation tasks with the web interface

class ContentType(object):
    """
    Class to represent a content type requested through content negotiation
    """
    def __init__(self, type=None, subtype=None, params=None, packaging=None):
        """
        Properties:
        type    - the main type of the content.  e.g. in text/html, the type is "text"
        subtype - the subtype of the content.  e.g. in text/html the subtype is "html"
        params  - as per the mime specification, his represents the parameter extension to the type, e.g. with
                    application/atom+xml;type=entry, the params are "type=entry"

        So, for example:
        application/atom+xml;type=entry => type="application", subtype="atom+xml", params="type=entry"
        """
        self.type = type
        self.subtype = subtype
        self.params = params
        self.packaging = packaging

    def from_mimetype(self, mimetype):
        # mimetype is of the form <supertype>/<subtype>[;<params>]
        parts = mimetype.split(";")
        if len(parts) == 2:
            self.type, self.subtype = parts[0].split("/", 1)
            self.params = parts[1]
        elif len(parts) == 1:
            self.type, self.subtype = parts[0].split("/", 1)

    def mimetype(self):
        """
        Turn the content type into its mimetype representation
        """
        mt = self.type + "/" + self.subtype
        if self.params is not None:
            mt += ";" + self.params
        return mt

    # NOTE: we only use this to construct a canonical form which includes the package to do comparisons over
    def media_format(self):
        mime = self.mimetype()
        pack = ""
        if self.packaging is not None:
            pack = "(packaging=\"" + self.packaging + "\") "
        mf = "(& (type=\"" + mime + "\") " + pack + ")"
        return mf

    def matches(self, other, packaging_wildcard=False):
        """
        Determine whether this ContentType and the supplied other ContentType are matches.  This includes full equality
        or whether the wildcards (*) which can be supplied for type or subtype properties are in place in either
        partner in the match.
        """
        tmatch = self.type == "*" or other.type == "*" or self.type == other.type
        smatch = self.subtype == "*" or other.subtype == "*" or self.subtype == other.subtype
        # FIXME: there is some ambiguity in mime as to whether the omission of the params part is the same as
        # a wildcard.  For the purposes of convenience we have assumed here that it is, otherwise a request for
        # */* will not match any content type which has parameters
        pmatch = self.params is None or other.params is None or self.params == other.params

        # A similar problem exists for packaging.  We allow the user to tell us if packaging should be
        # wildcard sensitive
        packmatch = False
        if packaging_wildcard:
            packmatch = self.packaging is None or other.packaging is None or self.packaging == other.packaging
        else:
            packmatch = self.packaging == other.packaging
        return tmatch and smatch and pmatch and packmatch

    def __eq__(self, other):
        return self.media_format() == other.media_format()

    def __str__(self):
        return self.media_format()

    def __repr__(self):
        return str(self)

class ContentNegotiator(object):
    """
    Class to manage content negotiation.  Given its input parameters it will provide a ContentType object which
    the server can use to locate its resources
    """
    def __init__(self):
        """
        There are 4 parameters which must be set in order to start content negotiation
        - acceptable    -   What ContentType objects are acceptable to return (in order of preference)
        - default_type  -   If no Accept header is found use this type
        - default_subtype   -   If no Accept header is found use this subtype
        - default_params    -   If no Accept header is found use this subtype
        """
        self.acceptable = []
        self.default_type = None
        self.default_subtype = None
        self.default_params = None
        self.default_packaging = None

    def get_accept(self, dict):
        """
        Get the Accept header out of the web.py HTTP dictionary.  Return None if no accept header exists
        """
        if dict.has_key("HTTP_ACCEPT"):
            return dict["HTTP_ACCEPT"]
        return None

    def get_packaging(self, dict):
        if dict.has_key('HTTP_ACCEPT_PACKAGING'):
            return dict['HTTP_ACCEPT_PACKAGING']
        return None

    def analyse_accept(self, accept, packaging=None):
        # FIXME: we need to somehow handle q=0.0 in here and in other related methods
        """
        Analyse the Accept header string from the HTTP headers and return a structured dictionary with each
        content types grouped by their common q values, thus:

        dict = {
            1.0 : [<ContentType>, <ContentType>],
            0.8 : [<ContentType],
            0.5 : [<ContentType>, <ContentType>]
        }

        This method will guarantee that ever content type has some q value associated with it, even if this was not
        supplied in the original Accept header; it will be inferred based on the rules of content negotiation
        """
        # accept headers are a list of content types and q values, in a comma separated list
        parts = accept.split(",")

        # set up some registries for the coming analysis.  unsorted will hold each part of the accept header following
        # its analysis, but without respect to its position in the preferences list.  highest_q and counter will be
        # recorded during this first run so that we can use them to sort the list later
        unsorted = []
        highest_q = 0.0
        counter = 0

        # go through each possible content type and analyse it along with its q value
        for part in parts:
            # count the part number that we are working on, starting from 1
            counter += 1

            # the components of the part can be "type;params;q" "type;params", "type;q" or just "type"
            components = part.split(";")

            # the first part is always the type (see above comment)
            type = components[0].strip()

            # create some default values for the other parts.  If there is no params, we will use None, if there is
            # no q we will use a negative number multiplied by the position in the list of this part.  This allows us
            # to later see the order in which the parts with no q value were listed, which is important
            params = None
            q = -1 * counter

            # There are then 3 possibilities remaining to check for: "type;q", "type;params" and "type;params;q"
            # ("type" is already handled by the default cases set up above)
            if len(components) == 2:
                # "type;q" or "type;params"
                if components[1].strip().startswith("q="):
                    # "type;q"
                    q = components[1].strip()[2:] # strip the "q=" from the start of the q value
                    # if the q value is the highest one we've seen so far, record it
                    if float(q) > highest_q:
                        highest_q = float(q)
                else:
                    # "type;params"
                    params = components[1].strip()
            elif len(components) == 3:
                # "type;params;q"
                params = components[1].strip()
                q = components[1].strip()[2:] # strip the "q=" from the start of the q value
                # if the q value is the highest one we've seen so far, record it
                if float(q) > highest_q:
                    highest_q = float(q)

            # at the end of the analysis we have all of the components with or without their default values, so we
            # just record the analysed version for the time being as a tuple in the unsorted array
            unsorted.append((type, params, q))

        # once we've finished the analysis we'll know what the highest explicitly requested q will be.  This may leave
        # us with a gap between 1.0 and the highest requested q, into which we will want to put the content types which
        # did not have explicitly assigned q values.  Here we calculate the size of that gap, so that we can use it
        # later on in positioning those elements.  Note that the gap may be 0.0.
        q_range = 1.0 - highest_q

        # set up a dictionary to hold our sorted results.  The dictionary will be keyed with the q value, and the
        # value of each key will be an array of ContentType objects (in no particular order)
        sorted = {}

        # go through the unsorted list
        for (type, params, q) in unsorted:
            # break the type into super and sub types for the ContentType constructor
            supertype, subtype = type.split("/", 1)
            if q > 0:
                # if the q value is greater than 0 it was explicitly assigned in the Accept header and we can just place
                # it into the sorted dictionary
                self.insert(sorted, q, ContentType(supertype, subtype, params, packaging))
            else:
                # otherwise, we have to calculate the q value using the following equation which creates a q value "qv"
                # within "q_range" of 1.0 [the first part of the eqn] based on the fraction of the way through the total
                # accept header list scaled by the q_range [the second part of the eqn]
                qv = (1.0 - q_range) + (((-1 * q)/counter) * q_range)
                self.insert(sorted, qv, ContentType(supertype, subtype, params, packaging))

        # now we have a dictionary keyed by q value which we can return
        return sorted

    def insert(self, d, q, v):
        """
        Utility method: if dict d contains key q, then append value v to the array which is identified by that key
        otherwise create a new key with the value of an array with a single value v
        """
        if d.has_key(q):
            d[q].append(v)
        else:
            d[q] = [v]

    def contains_match(self, source, target):
        """
        Does the target list of ContentType objects contain a match for the supplied source
        Args:
        - source:   A ContentType object which we want to see if it matches anything in the target
        - target:   A list of ContentType objects to try to match the source against
        Returns the matching ContentTYpe from the target list, or None if no such match
        """
        for ct in target:
            if source.matches(ct):
                # matches are symmetrical, so source.matches(ct) == ct.matches(source) so way round is irrelevant
                # we return the target's content type, as this is considered the definitive list of allowed
                # content types, while the source may contain wildcards
                return ct
        return None

    def get_acceptable(self, client, server):
        """
        Take the client content negotiation requirements - as returned by analyse_accept() - and the server's
        array of supported types (in order of preference) and determine the most acceptable format to return.

        This method always returns the client's most preferred format if the server supports it, irrespective of the
        server's preference.  If the client has no discernable preference between two formats (i.e. they have the same
        q value) then the server's preference is taken into account.

        Returns a ContentType object represening the mutually acceptable content type, or None if no agreement could
        be reached.
        """

        # get the client requirement keys sorted with the highest q first (the server is a list which should be
        # in order of preference already)
        ckeys = client.keys()
        ckeys.sort(reverse=True)

        # the rule for determining what to return is that "the client's preference always wins", so we look for the
        # highest q ranked item that the server is capable of returning.  We only take into account the server's
        # preference when the client has two equally weighted preferences - in that case we take the server's
        # preferred content type
        for q in ckeys:
            # for each q in order starting at the highest
            possibilities = client[q]
            allowable = []
            for p in possibilities:
                # for each content type with the same q value

                # find out if the possibility p matches anything in the server.  This uses the ContentType's
                # matches() method which will take into account wildcards, so content types like */* will match
                # appropriately.  We get back from this the concrete ContentType as specified by the server
                # if there is a match, so we know the result contains no unintentional wildcards
                match = self.contains_match(p, server)
                if match is not None:
                    # if there is a match, register it
                    allowable.append(match)

            # we now know if there are 0, 1 or many allowable content types at this q value
            if len(allowable) == 0:
                # we didn't find anything, so keep looking at the next q value
                continue
            elif len(allowable) == 1:
                # we found exactly one match, so this is our content type to use
                return allowable[0]
            else:
                # we found multiple supported content types at this q value, so now we need to choose the server's
                # preference
                for i in range(len(server)):
                    # iterate through the server explicitly by numerical position
                    if server[i] in allowable:
                        # when we find our first content type in the allowable list, it is the highest ranked server content
                        # type that is allowable, so this is our type
                        return server[i]

        # we've got to here without returning anything, which means that the client and server can't come to
        # an agreement on what content type they want and can deliver.  There's nothing more we can do!
        return None

    def negotiate(self, dict):
        """
        Main method for carrying out content negotiation over the supplied HTTP headers dictionary.
        Returns either the preferred ContentType as per the settings of the object, or None if no agreement could be
        reached
        """
        ssslog.debug("Fallback parameters are Accept: " + str(self.default_type) + "/" + str(self.default_subtype) + 
                        ";" + str(self.default_params) + " and Accept-Packaging: " + str(self.default_packaging))
        
        # get the accept header if available
        accept = self.get_accept(dict)
        packaging = self.get_packaging(dict)
        ssslog.debug("Accept Header: " + str(accept))
        ssslog.debug("Packaging: "+ str(packaging))

        if accept is None and packaging is None:
            # if it is not available just return the defaults
            return ContentType(self.default_type, self.default_subtype, self.default_params, self.default_packaging)

        if packaging is None:
            packaging = self.default_packaging
        
        if accept is None:
            accept = self.default_type + "/" + self.default_subtype
            if self.default_params is not None:
                accept += ";" + self.default_params
        
        ssslog.debug("Negotiating on Accept: " + str(accept) + " and Accept-Packaging: " + str(packaging))
        
        # get us back a dictionary keyed by q value which tells us the order of preference that the client has
        # requested
        analysed = self.analyse_accept(accept, packaging)

        ssslog.debug("Analysed Accept: " + str(analysed))

        # go through the analysed formats and cross reference them with the acceptable formats
        content_type = self.get_acceptable(analysed, self.acceptable)
        ssslog.debug("Accepted: " + str(content_type))

        # return the acceptable content type.  If this is None (which get_acceptable can return), then the caller
        # will know that we failed to negotiate a type and should 415 the client
        return content_type

# REQUEST/RESPONSE CLASSES
#######################################################################
# These classes are used as the glue between the web.py web interface layer and the underlying sword server, allowing
# them to exchange messages agnostically to the interface

class Auth(object):
    def __init__(self, by=None, obo=None, target_owner_unknown=False):
        self.by = by
        self.obo = obo
        self.target_owner_unknown = target_owner_unknown

    def success(self):
        return self.by is not None and not self.target_owner_unknown

class SWORDRequest(object):
    """
    General class to represent any sword request (such as deposit or delete)
    """
    def __init__(self):
        """
        There are 4 HTTP sourced properties:
        - on_behalf_of  - On-Behalf-Of in HTTP; the user being deposited on behalf of
        - packaging     - Packaging in HTTP; the packaging format being used
        - in_progress   - In-Progress in HTTP; whether the deposit is complete or not from a client perspective
        - metadata_relevant - Metadata-Relevant; whether or not the deposit contains relevant metadata
        """

        self.on_behalf_of = None
        self.packaging = "http://purl.org/net/sword/package/Binary" # if this isn't populated externally, use the default
        self.in_progress = False
        self.metadata_relevant = True # the server MAY assume that it is True
        self.auth = None
        self.content_md5 = None
        self.slug = None

    def set_by_header(self, key, value):
        """
        Convenience method to take a relevant HTTP header and its value and add it to this object.
        e.g. set_by_header("On-Behalf-Of", "richard")  Notice that the format of the headers used
        here is the web.py format which is all upper case, preceeding with HTTP_ with all - converted to _
        (for some unknown reason)
        """
        ssslog.debug("Setting Header %s : %s" % (key, value))
        if key == "HTTP_ON_BEHALF_OF":
            self.on_behalf_of = value
        elif key == "HTTP_PACKAGING" and value is not None:
            self.packaging = value
        elif key == "HTTP_IN_PROGRESS":
            self.in_progress = (value.strip() == "true")
        elif key == "HTTP_METADATA_RELEVANT":
            self.metadata_relevant = (value.strip() == "true")
        elif key == "HTTP_CONTENT_MD5":
            self.content_md5 = value
        elif key == "HTTP_SLUG":
            self.slug = value

class DepositRequest(SWORDRequest):
    """
    Class to represent a request to deposit some content onto the server
    """
    def __init__(self):
        """
        There are 3 content related properties:
        - content   -   the incoming content file to be deposited
        - atom      -   the incoming atom document to be deposited (may be None)
        - filename  -   the desired name of the incoming content
        """
        SWORDRequest.__init__(self)

        # content related
        self.content_type = "application/octet-stream"
        self.content = None
        self.atom = None
        self.filename = "unnamed.file"
        self.too_large = False

class DepositResponse(object):
    """
    Class to represent the response to a deposit request
    """
    def __init__(self):
        """
        Properties:
        - created   - was the resource created on the server
        - accepted  -   was the resource accepted by the server (but not yet created)
        - error_code    -   if there was an error, what HTTP status code
        - error     -   sword error document if relevant
        - receipt   -   deposit receipt if successful deposit
        - location  -   the Edit-URI which will be supplied to the client as the Location header in responses
        """
        self.created = False
        self.accepted = False
        self.error_code = None
        self.error = None
        self.receipt = None
        self.location = None

class MediaResourceResponse(object):
    """
    Class to represent the response to a request to retrieve the Media Resource
    """
    def __init__(self):
        """
        There are three properties:
        redirect    -   boolean, does the client need to be redirected to another URL for the media resource
        url         -   If redirect, then this is the URL to redirect the client to
        filepath    -   If not redirect, then this is the path to the file that the server should serve
        """
        self.redirect = False
        self.url = None
        self.filepath = None
        self.packaging = None

class DeleteRequest(SWORDRequest):
    """
    Class Representing a request to delete either the content or the container itself.
    """
    def __init__(self):
        """
        The properties of this class are as per SWORDRequest
        """
        SWORDRequest.__init__(self)

class DeleteResponse(object):
    """
    Class to represent the response to a request to delete the content or the container
    """
    def __init__(self):
        """
        There are 3 properties:
        error_code  -   if there was an error, the http code associated
        error       -   the sworderror if appropriate
        receipt     -   if successful and a request for deleting content (not container) the deposit receipt
        """
        self.error_code = None
        self.error = None
        self.receipt = None

# Operational SWORD Classes
#############################################################################
# Classes which carry out the grunt work of the SSS

class SWORDSpec(object):
    """
    Class which attempts to represent the specification itself.  Instead of being operational like the SWORDServer
    class, it attempts to just be able to interpret the supplied http headers and content bodies and turn them into
    the entities with which SWORD works.  The jury is out, in my mind, whether this class is a useful separation, but
    for what it's worth, here it is ...
    """
    def __init__(self):
        # The HTTP headers that are part of the specification (from a web.py perspective - don't be fooled, these
        # aren't the real HTTP header names - see the spec)
        self.sword_headers = [
            "HTTP_ON_BEHALF_OF", "HTTP_PACKAGING", "HTTP_IN_PROGRESS", "HTTP_METADATA_RELEVANT",
            "HTTP_CONTENT_MD5", "HTTP_SLUG", "HTTP_ACCEPT_PACKAGING"
        ]

        self.error_content_uri = "http://purl.org/net/sword/error/ErrorContent"
        self.error_checksum_mismatch_uri = "http://purl.org/net/sword/error/ErrorChecksumMismatch"
        self.error_bad_request_uri = "http://purl.org/net/sword/error/ErrorBadRequest"
        self.error_target_owner_unknown_uri = "http://purl.org/net/sword/error/TargetOwnerUnknown"
        self.error_mediation_not_allowed_uri = "http://purl.org/net/sword/error/MediationNotAllowed"
        self.error_method_not_allowed_uri = "http://purl.org/net/sword/error/MethodNotAllowed"
        self.error_max_upload_size_exceeded = "http://purl.org/net/sword/error/MaxUploadSizeExceeded"

    def validate_deposit_request(self, web, allow_multipart=True):
        dict = web.ctx.environ

        # get each of the allowed SWORD headers that can be validated and see if they do
        ip = dict.get("HTTP_IN_PROGRESS")
        if ip is not None and ip != "true" and ip != "false":
            return "In-Progress must be 'true' or 'false'"

        sm = dict.get("HTTP_METADATA_RELEVANT")
        if sm is not None and sm != "true" and sm != "false":
            return "Metadata-Relevant must be 'true' or 'false'"

        # there must be both an "atom" and "payload" input or data in web.data()
        webin = web.input()
        if len(webin) != 2 and len(webin) > 0:
            return "Multipart request does not contain exactly 2 parts"
        if len(webin) >= 2 and not webin.has_key("atom") and not webin.has_key("payload"):
            return "Multipart request must contain Content-Dispositions with names 'atom' and 'payload'"
        if len(webin) > 0 and not allow_multipart:
            return "Multipart request not permitted in this context"

        # if we get to here then we have a valid multipart or no multipart
        if len(webin) != 2: # if it is not multipart
            if web.data() is None: # and there is no content
                return "No content sent to the server"

        # validates
        return None

    def validate_delete_request(self, web):
        dict = web.ctx.environ

        # get each of the allowed SWORD headers that can be validated and see if they do
        ip = dict.get("HTTP_IN_PROGRESS")
        if ip is not None and ip != "true" and ip != "false":
            return "In-Progress must be 'true' or 'false'"

        sm = dict.get("HTTP_METADATA_RELEVANT")
        if sm is not None and sm != "true" and sm != "false":
            return "Metadata-Relevant must be 'true' or 'false'"
        
        # validates
        return None

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

        # now go through the headers and populate the Deposit object
        dict = web.ctx.environ

        # get the headers that have been provided.  Any headers which have not been provided have default values
        # supplied in the DepositRequest object's constructor
        ssslog.debug("Incoming HTTP headers: " + str(dict))
        empty_request = False
        for head in dict.keys():
            if head in self.sword_headers:
                d.set_by_header(head, dict[head])
            if head == "HTTP_CONTENT_DISPOSITION":
                ssslog.debug("Reading Header %s : %s" % (head, dict[head]))
                d.filename = self.extract_filename(dict[head])
                ssslog.debug("Extracted filename %s from %s" % (d.filename, dict[head]))
            if head == "CONTENT_TYPE":
                ssslog.debug("Reading Header %s : %s" % (head, dict[head]))
                ct = dict[head]
                d.content_type = ct
                if ct.startswith("application/atom+xml"):
                    atom_only = True
            if head == "CONTENT_LENGTH":
                ssslog.debug("Reading Header %s : %s" % (head, dict[head]))
                if dict[head] == "0":
                    empty_request = True
                cl = int(dict[head]) # content length as an integer
                if cl > global_configuration.max_upload_size:
                    d.too_large = True
                    return d

        # first we need to find out if this is a multipart or not
        webin = web.input()
        if len(webin) == 2:
            ssslog.info("Received multipart deposit request")
            d.atom = webin['atom']
            # read the zip file from the base64 encoded string
            d.content = base64.decodestring(webin['payload'])
        elif not empty_request:
            # if this wasn't a multipart, and isn't an empty request, then the data is in web.data().  This could be a binary deposit or
            # an atom entry deposit - reply on the passed/determined argument to determine which
            if atom_only:
                ssslog.info("Received Entry deposit request")
                d.atom = web.data()
            else:
                ssslog.info("Received Binary deposit request")
                d.content = web.data()

        # now just attach the authentication data and return
        d.auth = auth
        return d

    def extract_filename(self, cd):
        """ get the filename out of the content disposition header """
        # ok, this is a bit obtuse, but it was fun making it.  It's not hard to understand really, if you break
        # it down
        return cd[cd.find("filename=") + len("filename="):cd.find(";", cd.find("filename=")) if cd.find(";", cd.find("filename=")) > -1 else len(cd)]

    def get_delete(self, dict, auth=None):
        """
        Take a web.py web object and extract from it the parameters and content required for a SWORD delete request.
        It mainly extracts the HTTP headers which are relevant to delete, and for those not supplied provides thier
        defaults in the returned DeleteRequest object
        """
        d = DeleteRequest()

        # we just want to parse out the headers that are relevant
        for head in dict.keys():
            if head in self.sword_headers:
                d.set_by_header(head, dict[head])

        # now just attach the authentication data and return
        d.auth = auth
        return d

class SWORDServer(object):
    """
    The main SWORD Server class.  This class deals with all the CRUD requests as provided by the web.py HTTP
    handlers
    """
    def __init__(self):

        # get the configuration
        self.configuration = global_configuration

        # create a DAO for us to use
        self.dao = DAO()

        # create a Namespace object for us to use
        self.ns = Namespaces()

        # create a URIManager for us to use
        self.um = URIManager()

        # build the namespace maps that we will use during serialisation
        self.sdmap = {None : self.ns.APP_NS, "sword" : self.ns.SWORD_NS, "atom" : self.ns.ATOM_NS, "dcterms" : self.ns.DC_NS}
        self.cmap = {None: self.ns.ATOM_NS}
        self.drmap = {None: self.ns.ATOM_NS, "sword" : self.ns.SWORD_NS, "dcterms" : self.ns.DC_NS}
        self.smap = {"rdf" : self.ns.RDF_NS, "ore" : self.ns.ORE_NS, "sword" : self.ns.SWORD_NS}
        self.emap = {"sword" : self.ns.SWORD_NS, "atom" : self.ns.ATOM_NS}

    def exists(self, oid):
        """
        Does the specified object id exist?
        """
        collection, id = oid.split("/", 1)
        return self.dao.collection_exists(collection) and self.dao.container_exists(collection, id)

    def service_document(self, use_sub=False):
        """
        Construct the Service Document.  This takes the set of collections that are in the store, and places them in
        an Atom Service document as the individual entries
        """
        # Start by creating the root of the service document, supplying to it the namespace map in this first instance
        service = etree.Element(self.ns.APP + "service", nsmap=self.sdmap)

        # version element
        version = etree.SubElement(service, self.ns.SWORD + "version")
        version.text = self.configuration.sword_version

        # max upload size
        mus = etree.SubElement(service, self.ns.SWORD + "maxUploadSize")
        mus.text = str(self.configuration.max_upload_size)

        # workspace element
        workspace = etree.SubElement(service, self.ns.APP + "workspace")

        # title element
        title = etree.SubElement(workspace, self.ns.ATOM + "title")
        title.text = "Main Site"

        # now for each collection create a collection element
        for col in self.dao.get_collection_names():
            collection = etree.SubElement(workspace, self.ns.APP + "collection")
            collection.set("href", self.um.col_uri(col))

            # collection title
            ctitle = etree.SubElement(collection, self.ns.ATOM + "title")
            ctitle.text = "Collection " + col

            if not self.configuration.accept_nothing:
                # accepts declaration
                if self.configuration.app_accept is not None:
                    for acc in self.configuration.app_accept:
                        accepts = etree.SubElement(collection, self.ns.APP + "accept")
                        accepts.text = acc
                
                if self.configuration.multipart_accept is not None:
                    for acc in self.configuration.multipart_accept:
                        mraccepts = etree.SubElement(collection, self.ns.APP + "accept")
                        mraccepts.text = acc
                        mraccepts.set("alternate", "multipart-related")
            else:
                accepts = etree.SubElement(collection, self.ns.APP + "accept")

            # SWORD collection policy
            collectionPolicy = etree.SubElement(collection, self.ns.SWORD + "collectionPolicy")
            collectionPolicy.text = "Collection Policy"

            # Collection abstract
            abstract = etree.SubElement(collection, self.ns.DC + "abstract")
            abstract.text = "Collection Description"

            # support for mediation
            mediation = etree.SubElement(collection, self.ns.SWORD + "mediation")
            mediation.text = "true" if self.configuration.mediation else "false"

            # treatment
            treatment = etree.SubElement(collection, self.ns.SWORD + "treatment")
            treatment.text = "Treatment description"

            # SWORD packaging formats accepted
            for format in self.configuration.sword_accept_package:
                acceptPackaging = etree.SubElement(collection, self.ns.SWORD + "acceptPackaging")
                acceptPackaging.text = format

            # provide a sub service element if appropriate
            if use_sub:
                subservice = etree.SubElement(collection, self.ns.SWORD + "service")
                subservice.text = self.um.sd_uri(True)

        # pretty print and return
        return etree.tostring(service, pretty_print=True)

    def list_collection(self, id):
        """
        List the contents of a collection identified by the supplied id
        """
        # create an empty feed element for the collection
        feed = etree.Element(self.ns.ATOM + "feed", nsmap=self.cmap)

        # if the collection path does not exist, then return the empty feed
        cpath = os.path.join(self.configuration.store_dir, str(id))
        if not os.path.exists(cpath):
            return etree.tostring(feed, pretty_print=True)

        # list all of the containers in the collection
        parts = os.listdir(cpath)
        for part in parts:
            entry = etree.SubElement(feed, self.ns.ATOM + "entry")
            link = etree.SubElement(entry, self.ns.ATOM + "link")
            link.set("rel", "edit")
            link.set("href", self.um.edit_uri(id, part))

        # pretty print and return
        return etree.tostring(feed, pretty_print=True)

    def deposit_new(self, collection, deposit):
        """
        Take the supplied deposit and treat it as a new container with content to be created in the specified collection
        Args:
        -collection:    the ID of the collection to be deposited into
        -deposit:       the DepositRequest object to be processed
        Returns a DepositResponse object which will contain the Deposit Receipt or a SWORD Error
        """
        # check for standard possible errors, and throw if appropriate
        er = self.check_deposit_errors(deposit)
        if er is not None:
            return er

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.dao.collection_exists(collection):
            return None

        # create us a new container, passing in the Slug value (which may be None) as the proposed id
        id = self.dao.create_container(collection, deposit.slug)

        # store the incoming atom document if necessary
        if deposit.atom is not None:
            entry_ingester = self.configuration.entry_ingester()
            entry_ingester.ingest(collection, id, deposit.atom)

        # store the content file if one exists, and do some processing on it
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want
            
            # FIXME: because the deposit interpreter doesn't deal with multipart properly
            # we don't get the correct packaging format here if the package is anything
            # other than Binary
            packager = self.configuration.package_ingesters[deposit.packaging]()
            derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)
            
            # a list of identifiers which will resolve to the derived resources
            derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

        # the aggregation uri
        agg_uri = self.um.agg_uri(collection, id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(collection, id)

        # create the initial statement
        s = Statement()
        s.aggregation_uri = agg_uri
        s.rem_uri = edit_uri
        by = deposit.auth.by if deposit.auth is not None else None
        obo = deposit.auth.obo if deposit.auth is not None else None
        if deposit_uri is not None:
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        s.in_progress = deposit.in_progress
        s.aggregates = derived_resource_uris

        # store the statement by itself
        self.dao.store_statement(collection, id, s)

        # create the basic deposit receipt (which involves getting hold of the item's metadata first if it exists)
        metadata = self.dao.get_metadata(collection, id)
        receipt = self.deposit_receipt(collection, id, deposit, s, metadata)

        # store the deposit receipt
        self.dao.store_deposit_receipt(collection, id, receipt)

        # now augment the receipt with the details of this particular deposit
        # this handles None arguments, and converts the xml receipt into a string
        receipt = self.augmented_receipt(receipt, deposit_uri, derived_resource_uris)
        
        # finally, assemble the deposit response and return
        dr = DepositResponse()
        dr.receipt = receipt
        dr.location = edit_uri
        dr.created = True
        
        return dr

    def get_part(self, path):
        """
        Get a file handle to the part identified by the supplied path
        - path:     The URI part which is the path to the file
        """
        collection, id, fn = self.um.interpret_path(path)
        if self.dao.file_exists(collection, id, fn):
            route = self.dao.get_store_path(collection, id, fn)
            return open(route, "r")
        else:
            return None

    def get_media_resource(self, oid, content_type):
        """
        Get a representation of the media resource for the given id as represented by the specified content type
        -id:    The ID of the object in the store
        -content_type   A ContentType object describing the type of the object to be retrieved
        """
        # by the time this is called, we should already know that we can return this type, so there is no need for
        # any checking, we just get on with it

        ssslog.info("Request media type with media format: " + content_type.media_format())

        # ok, so break the id down into collection and object
        collection, id = self.um.interpret_oid(oid)

        # make a MediaResourceResponse object for us to use
        mr = MediaResourceResponse()

        # if the type/subtype is text/html, then we need to do a redirect.  This is equivalent to redirecting the
        # client to the splash page of the item on the server
        if content_type.mimetype() == "text/html":
            ssslog.info("Requested format is text/html ... redirecting client to web ui")
            mr.redirect = True
            mr.url = self.um.html_url(collection, id)
            return mr
        
        # call the appropriate packager, and get back the filepath for the response
        packager = self.configuration.package_disseminators[content_type.media_format()]()
        mr.filepath = packager.package(collection, id)
        mr.packaging = packager.get_uri()

        return mr
    
    def replace(self, oid, deposit):
        """
        Replace all the content represented by the supplied id with the supplied deposit
        Args:
        - oid:  the object ID in the store
        - deposit:  a DepositRequest object
        Return a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        # check for standard possible errors, and throw if appropriate
        er = self.check_deposit_errors(deposit)
        if er is not None:
            return er

        collection, id = self.um.interpret_oid(oid)

        # does the object directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return None
                
        # first figure out what to do about the metadata
        keep_atom = False
        if deposit.atom is not None:
            ssslog.info("Replace request has ATOM part - updating")
            entry_ingester = self.configuration.entry_ingester()
            entry_ingester.ingest(collection, id, deposit.atom)
            keep_atom = True
            
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
            ssslog.info("Replace request has file content - updating")
            
            # remove all the old files before adding the new.  We always leave
            # behind the metadata; this will be overwritten later if necessary
            self.dao.remove_content(collection, id, True, keep_atom)

            # store the content file
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)
            ssslog.debug("New incoming file stored with filename " + fn)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want.  Notice that we pass in the metadata_relevant flag, so the
            # packager won't overwrite the existing metadata if it isn't supposed to
            packager = self.configuration.package_ingesters[deposit.packaging]()
            derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)
            ssslog.debug("Resources derived from deposit: " + str(derived_resources))
        
            # a list of identifiers which will resolve to the derived resources
            derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)

        # the aggregation uri
        agg_uri = self.um.agg_uri(collection, id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(collection, id)

        # create the new statement
        s = Statement()
        s.aggregation_uri = agg_uri
        s.rem_uri = edit_uri
        if deposit_uri is not None:
            by = deposit.auth.by if deposit.auth is not None else None
            obo = deposit.auth.obo if deposit.auth is not None else None
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        s.in_progress = deposit.in_progress
        s.aggregates = derived_resource_uris

        # store the statement by itself
        self.dao.store_statement(collection, id, s)

        # create the deposit receipt (which involves getting hold of the item's metadata first if it exists
        metadata = self.dao.get_metadata(collection, id)
        receipt = self.deposit_receipt(collection, id, deposit, s, metadata)

        # store the deposit receipt also
        self.dao.store_deposit_receipt(collection, id, receipt)
        
        # now augment the receipt with the details of this particular deposit
        # this handles None arguments, and converts the xml receipt into a string
        receipt = self.augmented_receipt(receipt, deposit_uri, derived_resource_uris)

        # finally, assemble the deposit response and return
        dr = DepositResponse()
        dr.receipt = receipt
        dr.location = edit_uri
        dr.created = True
        return dr

    def delete_content(self, oid, delete):
        """
        Delete all of the content from the object identified by the supplied id.  the parameters of the delete
        request must also be supplied
        - oid:  The ID of the object to delete the contents of
        - delete:   The DeleteRequest object
        Return a DeleteResponse containing the Deposit Receipt or the SWORD Error
        """
        ssslog.info("Deleting content of resource " + oid)
        
        # check for standard possible errors, and throw if appropriate
        er = self.check_delete_errors(delete)
        if er is not None:
            return er

        collection, id = self.um.interpret_oid(oid)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return None

        # remove all the old files before adding the new.
        # notice that we keep the metadata, as this is considered bound to the
        # container and not the media resource.
        self.dao.remove_content(collection, id, True)

        # the aggregation uri
        agg_uri = self.um.agg_uri(collection, id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(collection, id)

        # create the statement
        s = Statement()
        s.aggregation_uri = agg_uri
        s.rem_uri = edit_uri
        s.in_progress = delete.in_progress

        # store the statement by itself
        self.dao.store_statement(collection, id, s)

        # create the deposit receipt (which involves getting hold of the item's metadata first if it exists
        metadata = self.dao.get_metadata(collection, id)
        receipt = self.deposit_receipt(collection, id, delete, s, metadata)

        # store the deposit receipt also
        self.dao.store_deposit_receipt(collection, id, receipt)

        # finally, assemble the delete response and return
        dr = DeleteResponse()
        dr.receipt = receipt
        return dr
        
    def add_content(self, oid, deposit):
        """
        Take the supplied deposit and treat it as a new container with content to be created in the specified collection
        Args:
        -collection:    the ID of the collection to be deposited into
        -deposit:       the DepositRequest object to be processed
        Returns a DepositResponse object which will contain the Deposit Receipt or a SWORD Error
        """
        ssslog.info("Adding content to media resource of container " + oid)
        
        # check for standard possible errors, and throw if appropriate
        er = self.check_deposit_errors(deposit)
        if er is not None:
            return er

        collection, id = self.um.interpret_oid(oid)
        
        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return None

        # load the statement
        s = self.dao.load_statement(collection, id)
        s.in_progress = deposit.in_progress
        
        # store the content file if one exists, and do some processing on it
        location_uri = None
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
            ssslog.debug("Add request contains content part")
            
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)
            ssslog.debug("New incoming file stored with filename " + fn)
                
            packager = self.configuration.package_ingesters[deposit.packaging]()
            derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)
            ssslog.debug("Resources derived from deposit: " + str(derived_resources))

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)
            
            by = deposit.auth.by if deposit.auth is not None else None
            obo = deposit.auth.obo if deposit.auth is not None else None
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
            
            # a list of identifiers which will resolve to the derived resources
            derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)
            
            # decide on the location URI (it differs depending on whether this was
            # an unpackable resource or not
            if deposit.packaging == "http://purl.org/net/sword/package/Binary":
                location_uri = deposit_uri
            else:
                location_uri = self.um.em_uri(collection, id)
        
        # store the statement by itself
        self.dao.store_statement(collection, id, s)

        # create the deposit receipt (which involves getting hold of the item's metadata first if it exists
        metadata = self.dao.get_metadata(collection, id)
        receipt = self.deposit_receipt(collection, id, deposit, s, metadata)

        # store the deposit receipt also
        self.dao.store_deposit_receipt(collection, id, receipt)
        
        # now augment the receipt with the details of this particular deposit
        # this handles None arguments, and converts the xml receipt into a string
        receipt = self.augmented_receipt(receipt, deposit_uri, derived_resource_uris)

        # finally, assemble the deposit response and return
        dr = DepositResponse()
        dr.receipt = receipt
        dr.location = location_uri
        dr.created = True
        return dr

    def get_container(self, oid, content_type):
        """
        Get a representation of the container in the requested content type
        Args:
        -oid:   The ID of the object in the store
        -content_type   A ContentType object describing the required format
        Returns a representation of the container in the appropriate format
        """
        # by the time this is called, we should already know that we can return this type, so there is no need for
        # any checking, we just get on with it

        ssslog.info("Container requested in mime format: " + content_type.mimetype())

        # ok, so break the id down into collection and object
        collection, id = self.um.interpret_oid(oid)

        # pick either the deposit receipt or the pure statement to return to the client
        if content_type.mimetype() == "application/atom+xml;type=entry":
            return self.dao.get_deposit_receipt_content(collection, id)
        elif content_type.mimetype() == "application/rdf+xml":
            return self.dao.get_statement_content(collection, id)
        elif content_type.mimetype() == "application/atom+xml;type=feed":
            return self.dao.get_statement_feed(collection, id)
        else:
            ssslog.info("Requested mimetype not recognised/supported: " + content_type.mimetype())
            return None

    def deposit_existing(self, oid, deposit):
        """
        Deposit the incoming content into an existing object as identified by the supplied identifier
        Args:
        -oid:   The ID of the object we are depositing into
        -deposit:   The DepositRequest object
        Returns a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        ssslog.debug("Deposit onto an existing container " + oid)
        
        # check for standard possible errors, and throw if appropriate
        er = self.check_deposit_errors(deposit)
        if er is not None:
            return er

        collection, id = self.um.interpret_oid(oid)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return None

        # load the statement
        s = self.dao.load_statement(collection, id)
        
        # do the in-progress first, as some deposits will be empty, and will
        # just be telling us that the client has finished working on this item
        s.in_progress = deposit.in_progress
        
        # just do some useful logging
        if deposit.atom is None and deposit.content is None:
            ssslog.info("Empty deposit request; therefore this is just completing a previously incomplete deposit")
        
        # now just store the atom file and the content (this may overwrite an existing atom document - this is
        # intentional, although real servers would augment the existing metadata rather than overwrite)
        if deposit.atom is not None:
            ssslog.info("Append request has ATOM part - adding")
            
            # when we ingest the atom file, the existing atom doc may get overwritten,
            # but the spec requires that we only add metadata, not overwrite anything
            # (if possible).  For a purist implementation, then, we mark additive=True
            # in the call to the ingest method, so all metadata is added to whatever
            # is already there
            entry_ingester = self.configuration.entry_ingester()
            entry_ingester.ingest(collection, id, deposit.atom, True)

        # store the content file
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
            ssslog.info("Append request has file content - adding to media resource")
            
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)
            ssslog.debug("New incoming file stored with filename " + fn)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want.  Notice that we pass in the metadata_relevant flag, so the packager
            # won't overwrite the metadata if it isn't supposed to
            pclass = self.configuration.package_ingesters.get(deposit.packaging)
            if pclass is not None:
                packager = pclass()
                derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)
                ssslog.debug("Resources derived from deposit: " + str(derived_resources))
                
                # a list of identifiers which will resolve to the derived resources
                derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)

            # add the new deposit
            by = deposit.auth.by if deposit.auth is not None else None
            obo = deposit.auth.obo if deposit.auth is not None else None
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        
        # add the new list of aggregations to the existing list, allowing the
        # statement to ensure that the list is normalised (only consisting of
        # unique uris)
        s.add_normalised_aggregations(derived_resource_uris)
        
        # store the statement by itself
        self.dao.store_statement(collection, id, s)

        # create the deposit receipt (which involves getting hold of the item's metadata first if it exists
        metadata = self.dao.get_metadata(collection, id)
        receipt = self.deposit_receipt(collection, id, deposit, s, metadata)

        # store the deposit receipt also
        self.dao.store_deposit_receipt(collection, id, receipt)
        
        # now augment the receipt with the details of this particular deposit
        # this handles None arguments, and converts the xml receipt into a string
        receipt = self.augmented_receipt(receipt, deposit_uri, derived_resource_uris)

        # finally, assemble the deposit response and return
        dr = DepositResponse()
        dr.receipt = receipt
        # NOTE: in the spec, this is different for 6.7.2 and 6.7.3 (edit-iri and eiri respectively)
        # in this case, we have always gone for the approach of 6.7.2, and contend that the
        # spec is INCORRECT for 6.7.3 (also, section 9.3, which comes into play here
        # also says use the edit-uri)
        dr.location = self.um.edit_uri(collection, id) 
        dr.created = True
        return dr

    def delete_container(self, oid, delete):
        """
        Delete the entire object in the store
        Args:
        -oid:   The ID of the object in the store
        -delete:    The DeleteRequest object
        Return a DeleteResponse object with may contain a SWORD Error document or nothing at all
        """
        # check for standard possible errors, and throw if appropriate
        er = self.check_delete_errors(delete)
        if er is not None:
            return er
            
        collection, id = self.um.interpret_oid(oid)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return None

        # request the deletion of the container
        self.dao.remove_container(collection, id)
        return DeleteResponse()

    def get_derived_resource_uris(self, collection, id, derived_resource_names):
        uris = []
        for name in derived_resource_names:
            uris.append(self.um.part_uri(collection, id, name))
        return uris

    def augmented_receipt(self, receipt, original_deposit_uri, derived_resource_uris=[]):
        # Original Deposit
        if original_deposit_uri is not None:
            od = etree.SubElement(receipt, self.ns.ATOM + "link")
            od.set("rel", "http://purl.org/net/sword/terms/originalDeposit")
            od.set("href", original_deposit_uri)
        
        # Derived Resources
        if derived_resource_uris is not None:
            for uri in derived_resource_uris:
                dr = etree.SubElement(receipt, self.ns.ATOM + "link")
                dr.set("rel", "http://purl.org/net/sword/terms/derivedResource")
                dr.set("href", uri)
            
        return etree.tostring(receipt, pretty_print=True)

    def deposit_receipt(self, collection, id, deposit, statement, metadata):
        """
        Construct a deposit receipt document for the provided URIs
        Args:
        -deposit_id:    The Atom Entry ID to use
        -cont_uri:   The Cont-URI from which the media resource content can be retrieved
        -em_uri:    The EM-URI (Edit Media) at which operations on the media resource can be conducted
        -edit_uri:  The Edit-URI at which operations on the container can be conducted
        -statement: A Statement object to be embedded in the receipt as foreign markup (deprecated)
        Returns a string representation of the deposit receipt
        """
        # assemble the URIs we are going to need
        
        # the atom entry id
        drid = self.um.atom_id(collection, id)

        # the Cont-URI
        cont_uri = self.um.cont_uri(collection, id)

        # the EM-URI and SE-IRI
        em_uri = self.um.em_uri(collection, id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(collection, id)
        se_uri = edit_uri

        # the splash page URI
        splash_uri = self.um.html_url(collection, id)

        # the two statement uris
        atom_statement_uri = self.um.state_uri(collection, id, "atom")
        ore_statement_uri = self.um.state_uri(collection, id, "ore")

        # ensure that there is a metadata object, and that it is populated with enough information to build the
        # deposit receipt
        if metadata is None:
            metadata = {}
        if not metadata.has_key("title"):
            metadata["title"] = ["SWORD Deposit"]
        if not metadata.has_key("creator"):
            metadata["creator"] = ["SWORD Client"]
        if not metadata.has_key("abstract"):
            metadata["abstract"] = ["Content deposited with SWORD client"]

        # Now assemble the deposit receipt

        # the main entry document room
        entry = etree.Element(self.ns.ATOM + "entry", nsmap=self.drmap)

        # Title from metadata
        title = etree.SubElement(entry, self.ns.ATOM + "title")
        title.text = metadata['title'][0]

        # Atom Entry ID
        id = etree.SubElement(entry, self.ns.ATOM + "id")
        id.text = drid

        # Date last updated (i.e. NOW)
        updated = etree.SubElement(entry, self.ns.ATOM + "updated")
        updated.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Author field from metadata
        author = etree.SubElement(entry, self.ns.ATOM + "author")
        name = etree.SubElement(author, self.ns.ATOM + "name")
        name.text = metadata['creator'][0]

        # Summary field from metadata
        summary = etree.SubElement(entry, self.ns.ATOM + "summary")
        summary.set("type", "text")
        summary.text = metadata['abstract'][0]

        
        # Generator - identifier for this server software
        generator = etree.SubElement(entry, self.ns.ATOM + "generator")
        generator.set("uri", "http://www.swordapp.org/sss")
        generator.set("version", "1.0")

        # now embed all the metadata as foreign markup
        for field in metadata.keys():
            for v in metadata[field]:
                fdc = etree.SubElement(entry, self.ns.DC + field)
                fdc.text = v

        # verbose description
        vd = etree.SubElement(entry, self.ns.SWORD + "verboseDescription")
        vd.text = "SSS has done this, that and the other to process the deposit"

        # treatment
        treatment = etree.SubElement(entry, self.ns.SWORD + "treatment")
        treatment.text = "Treatment description"

        # link to splash page
        alt = etree.SubElement(entry, self.ns.ATOM + "link")
        alt.set("rel", "alternate")
        alt.set("href", splash_uri)

        # Media Resource Content URI (Cont-URI)
        content = etree.SubElement(entry, self.ns.ATOM + "content")
        content.set("type", "application/zip")
        content.set("src", cont_uri)

        # Edit-URI
        editlink = etree.SubElement(entry, self.ns.ATOM + "link")
        editlink.set("rel", "edit")
        editlink.set("href", edit_uri)
        
        # EM-URI (Media Resource)
        emlink = etree.SubElement(entry, self.ns.ATOM + "link")
        emlink.set("rel", "edit-media")
        emlink.set("href", em_uri)
        emfeedlink = etree.SubElement(entry, self.ns.ATOM + "link")
        emfeedlink.set("rel", "edit-media")
        emfeedlink.set("type", "application/atom+xml;type=feed")
        emfeedlink.set("href", em_uri + ".atom")

        # SE-URI (Sword edit - same as media resource)
        selink = etree.SubElement(entry, self.ns.ATOM + "link")
        selink.set("rel", "http://purl.org/net/sword/terms/add")
        selink.set("href", se_uri)

        # supported packaging formats
        for disseminator in self.configuration.sword_disseminate_package:
            sp = etree.SubElement(entry, self.ns.SWORD + "packaging")
            sp.text = disseminator

        # now the two statement uris
        state1 = etree.SubElement(entry, self.ns.ATOM + "link")
        state1.set("rel", "http://purl.org/net/sword/terms/statement")
        state1.set("type", "application/atom+xml;type=feed")
        state1.set("href", atom_statement_uri)

        state2 = etree.SubElement(entry, self.ns.ATOM + "link")
        state2.set("rel", "http://purl.org/net/sword/terms/statement")
        state2.set("type", "application/rdf+xml")
        state2.set("href", ore_statement_uri)

        return entry

    def get_statement(self, oid, content_type):
        collection, id = self.um.interpret_oid(oid)
        if content_type == "application/rdf+xml":
            return self.dao.get_statement_content(collection, id)
        elif content_type == "application/atom+xml;type=feed":
            return self.dao.get_statement_feed(collection, id)
        else:
            return None

    def sword_error(self, uri, msg=None):
        entry = etree.Element(self.ns.SWORD + "error", nsmap=self.emap)
        entry.set("href", uri)

        author = etree.SubElement(entry, self.ns.ATOM + "author")
        name = etree.SubElement(author, self.ns.ATOM + "name")
        name.text = "SSS"

        title = etree.SubElement(entry, self.ns.ATOM + "title")
        title.text = "ERROR: " + uri

        # Date last updated (i.e. NOW)
        updated = etree.SubElement(entry, self.ns.ATOM + "updated")
        updated.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Generator - identifier for this server software
        generator = etree.SubElement(entry, self.ns.ATOM + "generator")
        generator.set("uri", "http://www.swordapp.org/sss")
        generator.set("version", "1.0")

        # Summary field from metadata
        summary = etree.SubElement(entry, self.ns.ATOM + "summary")
        summary.set("type", "text")
        text = "Error Description: " + uri
        if msg is not None:
            text += " ; " + msg
        summary.text = text

        # treatment
        treatment = etree.SubElement(entry, self.ns.SWORD + "treatment")
        treatment.text = "processing failed"
        
        # verbose description
        vb = etree.SubElement(entry, self.ns.SWORD + "verboseDescription")
        vb.text = "Verbose Description Here"

        return etree.tostring(entry, pretty_print=True)

    def check_delete_errors(self, delete):
        # have we been asked to do a mediated delete, when this is not allowed?
        if delete.auth is not None:
            if delete.auth.obo is not None and not self.configuration.mediation:
                spec = SWORDSpec()
                dr = DepositResponse()
                error_doc = self.sword_error(spec.error_mediation_not_allowed_uri)
                dr.error = error_doc
                dr.error_code = "412 Precondition Failed"
                return dr
        return None

    def check_mediated_error(self, deposit):
        # have we been asked to do a mediated deposit, when this is not allowed?
        if deposit.auth is not None:
            if deposit.auth.obo is not None and not self.configuration.mediation:
                spec = SWORDSpec()
                dr = DepositResponse()
                error_doc = self.sword_error(spec.error_mediation_not_allowed_uri)
                dr.error = error_doc
                dr.error_code = "412 Precondition Failed"
                return dr
        return None

    def check_deposit_errors(self, deposit):
        # have we been asked for an invalid package format
        if deposit.packaging == self.configuration.error_content_package:
            spec = SWORDSpec()
            dr = DepositResponse()
            error_doc = self.sword_error(spec.error_content_uri, "Unsupported Packaging format specified")
            dr.error = error_doc
            dr.error_code = "415 Unsupported Media Type"
            return dr

        # have we been given an incompatible MD5?
        if deposit.content_md5 is not None:
            m = hashlib.md5()
            m.update(deposit.content)
            digest = m.hexdigest()
            if digest != deposit.content_md5:
                spec = SWORDSpec()
                dr = DepositResponse()
                error_doc = self.sword_error(spec.error_checksum_mismatch_uri, "Content-MD5 header does not match file checksum")
                dr.error = error_doc
                dr.error_code = "412 Precondition Failed"
                return dr

        # have we been asked to do a mediated deposit, when this is not allowed?
        if deposit.auth is not None:
            if deposit.auth.obo is not None and not self.configuration.mediation:
                spec = SWORDSpec()
                dr = DepositResponse()
                error_doc = self.sword_error(spec.error_mediation_not_allowed_uri)
                dr.error = error_doc
                dr.error_code = "412 Precondition Failed"
                return dr

        return None

class Statement(object):
    """
    Class representing the Statement; a description of the object as it appears on the server
    """
    def __init__(self):
        """
        The statement has 4 important properties:
        - aggregation_uri   -   The URI of the aggregation in ORE terms
        - rem_uri           -   The URI of the Resource Map in ORE terms
        - original_deposits -   The list of original packages uploaded to the server (set with original_deposit())
        - in_progress       -   Is the submission in progress (boolean)
        - aggregates        -   the non-original deposit files associated with the item
        """
        self.aggregation_uri = None
        self.rem_uri = None
        self.original_deposits = []
        self.aggregates = []
        self.in_progress = False

        # URIs to use for the two supported states in SSS
        self.in_progress_uri = "http://purl.org/net/sword/state/in-progress"
        self.archived_uri = "http://purl.org/net/sword/state/archived"

        # the descriptions to associated with the two supported states in SSS
        self.states = {
            self.in_progress_uri : "The work is currently in progress, and has not passed to a reviewer",
            self.archived_uri : "The work has passed through review and is now in the archive"
        }

        # Namespace map for XML serialisation
        self.ns = Namespaces()
        self.smap = {"rdf" : self.ns.RDF_NS, "ore" : self.ns.ORE_NS, "sword" : self.ns.SWORD_NS}
        self.asmap = {"oreatom" : self.ns.ORE_ATOM_NS, "atom" : self.ns.ATOM_NS, "rdf" : self.ns.RDF_NS, "ore" : self.ns.ORE_NS, "sword" : self.ns.SWORD_NS}
        self.fmap = {"atom" : self.ns.ATOM_NS, "sword" : self.ns.SWORD_NS}

    def __str__(self):
        return str(self.aggregation_uri) + ", " + str(self.rem_uri) + ", " + str(self.original_deposits)
        
    def original_deposit(self, uri, deposit_time, packaging_format, by, obo):
        """
        Add an original deposit to the statement
        Args:
        - uri:  The URI to the original deposit
        - deposit_time:     When the deposit was originally made
        - packaging_format:     The package format of the deposit, as supplied in the Packaging header
        """
        self.original_deposits.append((uri, deposit_time, packaging_format, by, obo))

    def add_normalised_aggregations(self, aggs):
        for agg in aggs:
            if agg not in self.aggregates:
                self.aggregates.append(agg)

    def load(self, filepath):
        """
        Populate this statement object from the XML serialised statement to be found at the specified filepath
        """
        f = open(filepath, "r")
        rdf = etree.fromstring(f.read())
        
        aggs = []
        ods = []
        for desc in rdf.getchildren():
            packaging = None
            depositedOn = None
            deposit_by = None
            deposit_obo = None
            about = desc.get(self.ns.RDF + "about")
            for element in desc.getchildren():
                if element.tag == self.ns.ORE + "aggregates":
                    resource = element.get(self.ns.RDF + "resource")
                    aggs.append(resource)
                if element.tag == self.ns.ORE + "describes":
                    resource = element.get(self.ns.RDF + "resource")
                    self.aggregation_uri = resource
                    self.rem_uri = about
                if element.tag == self.ns.SWORD + "state":
                    state = element.get(self.ns.RDF + "resource")
                    self.in_progress = state == "http://purl.org/net/sword/state/in-progress"
                if element.tag == self.ns.SWORD + "packaging":
                    packaging = element.get(self.ns.RDF + "resource")
                if element.tag == self.ns.SWORD + "depositedOn":
                    deposited = element.text
                    depositedOn = datetime.strptime(deposited, "%Y-%m-%dT%H:%M:%SZ")
                if element.tag == self.ns.SWORD + "depositedBy":
                    deposit_by = element.text
                if element.tag == self.ns.SWORD + "depositedOnBehalfOf":
                    deposit_obo = element.text
            if packaging is not None:
                ods.append(about)
                self.original_deposit(about, depositedOn, packaging, deposit_by, deposit_obo)
        
        # sort out the ordinary aggregations from the original deposits
        self.aggregates = []
        for agg in aggs:
            if agg not in ods:
                self.aggregates.append(agg)

    def serialise(self):
        """
        Serialise this statement into an RDF/XML string
        """
        rdf = self.get_rdf_xml()
        return etree.tostring(rdf, pretty_print=True)

    def serialise_atom(self):
        """
        Serialise this statement to an Atom Feed document
        """
        # create the root atom feed element
        feed = etree.Element(self.ns.ATOM + "feed", nsmap=self.fmap)

        # create the sword:state term in the root of the feed
        state_uri = self.in_progress_uri if self.in_progress else self.archived_uri
        state = etree.SubElement(feed, self.ns.SWORD + "state")
        state.set("href", state_uri)
        meaning = etree.SubElement(state, self.ns.SWORD + "stateDescription")
        meaning.text = self.states[state_uri]

        # now do an entry for each original deposit
        for (uri, datestamp, format_uri, by, obo) in self.original_deposits:
            # FIXME: this is not an official atom entry yet
            entry = etree.SubElement(feed, self.ns.ATOM + "entry")

            category = etree.SubElement(entry, self.ns.ATOM + "category")
            category.set("scheme", self.ns.SWORD_NS)
            category.set("term", self.ns.SWORD_NS + "originalDeposit")
            category.set("label", "Orignal Deposit")

            # Media Resource Content URI (Cont-URI)
            content = etree.SubElement(entry, self.ns.ATOM + "content")
            content.set("type", "application/zip")
            content.set("src", uri)

            # add all the foreign markup

            format = etree.SubElement(entry, self.ns.SWORD + "packaging")
            format.text = format_uri

            deposited = etree.SubElement(entry, self.ns.SWORD + "depositedOn")
            deposited.text = datestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

            deposit_by = etree.SubElement(entry, self.ns.SWORD + "depositedBy")
            deposit_by.text = by

            if obo is not None:
                deposit_obo = etree.SubElement(entry, self.ns.SWORD + "depositedOnBehalfOf")
                deposit_obo.text = obo

        # finally do an entry for all the ordinary aggregated resources
        for uri in self.aggregates:
            entry = etree.SubElement(feed, self.ns.ATOM + "entry")
            content = etree.SubElement(entry, self.ns.ATOM + "content")
            content.set("type", "application/octet-stream")
            content.set("src", uri)

        return etree.tostring(feed, pretty_print=True)

    def get_rdf_xml(self):
        """
        Get an lxml Element object back representing this statement
        """

        # we want to create an ORE resource map, and also add on the sword specific bits for the original deposits and the state

        # create the RDF root
        rdf = etree.Element(self.ns.RDF + "RDF", nsmap=self.smap)

        # in the RDF root create a Description for the REM which ore:describes the Aggregation
        description1 = etree.SubElement(rdf, self.ns.RDF + "Description")
        description1.set(self.ns.RDF + "about", self.rem_uri)
        describes = etree.SubElement(description1, self.ns.ORE + "describes")
        describes.set(self.ns.RDF + "resource", self.aggregation_uri)

        # in the RDF root create a Description for the Aggregation which is ore:isDescribedBy the REM
        description = etree.SubElement(rdf, self.ns.RDF + "Description")
        description.set(self.ns.RDF + "about", self.aggregation_uri)
        idb = etree.SubElement(description, self.ns.ORE + "isDescribedBy")
        idb.set(self.ns.RDF + "resource", self.rem_uri)

        # Create ore:aggreages for all ordinary aggregated files
        for uri in self.aggregates:
            aggregates = etree.SubElement(description, self.ns.ORE + "aggregates")
            aggregates.set(self.ns.RDF + "resource", uri)

        # Create ore:aggregates and sword:originalDeposit relations for the original deposits
        for (uri, datestamp, format, by, obo) in self.original_deposits:
            # standard ORE aggregates statement
            aggregates = etree.SubElement(description, self.ns.ORE + "aggregates")
            aggregates.set(self.ns.RDF + "resource", uri)

            # assert that this is an original package
            original = etree.SubElement(description, self.ns.SWORD + "originalDeposit")
            original.set(self.ns.RDF + "resource", uri)

        # now do the state information
        state_uri = self.in_progress_uri if self.in_progress else self.archived_uri
        state = etree.SubElement(description, self.ns.SWORD + "state")
        state.set(self.ns.RDF + "resource", state_uri)

        # Build the Description elements for the original deposits, with their sword:depositedOn and sword:packaging
        # relations
        for (uri, datestamp, format_uri, by, obo) in self.original_deposits:
            desc = etree.SubElement(rdf, self.ns.RDF + "Description")
            desc.set(self.ns.RDF + "about", uri)

            format = etree.SubElement(desc, self.ns.SWORD + "packaging")
            format.set(self.ns.RDF + "resource", format_uri)

            deposited = etree.SubElement(desc, self.ns.SWORD + "depositedOn")
            deposited.set(self.ns.RDF + "datatype", "http://www.w3.org/2001/XMLSchema#dateTime")
            deposited.text = datestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

            deposit_by = etree.SubElement(desc, self.ns.SWORD + "depositedBy")
            deposit_by.set(self.ns.RDF + "datatype", "http://www.w3.org/2001/XMLSchema#string")
            deposit_by.text = by

            if obo is not None:
                deposit_obo = etree.SubElement(desc, self.ns.SWORD + "depositedOnBehalfOf")
                deposit_obo.set(self.ns.RDF + "datatype", "http://www.w3.org/2001/XMLSchema#string")
                deposit_obo.text = obo

        # finally do a description for the state
        sdesc = etree.SubElement(rdf, self.ns.RDF + "Description")
        sdesc.set(self.ns.RDF + "about", state_uri)
        meaning = etree.SubElement(sdesc, self.ns.SWORD + "stateDescription")
        meaning.text = self.states[state_uri]

        return rdf

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

class DAO(object):
    """
    Data Access Object for interacting with the store
    """
    def __init__(self):
        """
        Initialise the DAO.  This creates the store directory in the Configuration() object if it does not already
        exist and will construct the relevant number of fake collections.  In general if you make changes to the
        number of fake collections you want to have, it's best just to burn the store and start from scratch, although
        this method will check to see that it has enough fake collections and make up the defecit, but it WILL NOT
        remove excess collections
        """
        self.configuration = global_configuration

        # first thing to do is create the store if it does not already exist
        print self.configuration.store_dir
        if not os.path.exists(self.configuration.store_dir):
            os.makedirs(self.configuration.store_dir)

        # now construct the fake collections
        current_cols = os.listdir(self.configuration.store_dir)
        create = self.configuration.num_collections - len(current_cols)
        for i in range(create):
            name = str(uuid.uuid4())
            cdir = os.path.join(self.configuration.store_dir, name)
            os.makedirs(cdir)

        self.ns = Namespaces()
        self.mdmap = {None : self.ns.DC_NS}

    def get_collection_names(self):
        """ list all the collections in the store """
        return os.listdir(self.configuration.store_dir)

    def collection_exists(self, collection):
        """
        Does the specified collection exist?
        Args:
        -collection:    the Collection name
        Returns true or false
        """
        cdir = os.path.join(self.configuration.store_dir, collection)
        return os.path.exists(cdir)

    def container_exists(self, collection, id):
        """
        Does the specified container exist?  If the collection does not exist this will still return and will return
        false
        Args:
        -collection:    the Collection name
        -id:    the container id
        Returns true or false
        """
        odir = os.path.join(self.configuration.store_dir, collection, id)
        return os.path.exists(odir)

    def file_exists(self, collection, id, filename):
        fpath = os.path.join(self.configuration.store_dir, collection, id, filename)
        return os.path.exists(fpath)

    def create_container(self, collection, id=None):
        """
        Create a container in the specified collection.  The container will be assigned a random UUID as its
        identifier.
        Args:
        -collection:    the collection name in which to create the container
        Returns the ID of the container
        """
        # invent an identifier for the item, and create its directory
        # we may have been passed an ID to use
        if id is None:
            id = str(uuid.uuid4())
        odir = os.path.join(self.configuration.store_dir, collection, id)
        if not os.path.exists(odir):
            os.makedirs(odir)
        return id

    def save(self, filepath, content, opts="w"):
        """
        Shortcut to save the content to the filepath with the associated file handle opts (defaults to "w", so pass
        in "wb" for binary files
        """
        f = open(filepath, opts)
        f.write(content)
        f.close()

    def get_filename(self, filename):
        """
        Create a timestamped file name to avoid name clashes in the store
        """
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ") + "_" + filename

    def store_atom(self, collection, id, atom):
        """ Store the supplied atom document content in the object identified by the id in the specified collection """
        afile = os.path.join(self.configuration.store_dir, collection, id, "atom.xml")
        self.save(afile, atom)

    def store_content(self, collection, id, content, filename):
        """
        Store the supplied content in the object identified by the id in the specified collection under the supplied
        filename.  In reality, to avoid name colisions the filename will be preceeded with a timestamp in the store.
        Returns the localised filename the content was stored under
        """
        ufn = self.get_filename(filename)
        cfile = os.path.join(self.configuration.store_dir, collection, id, ufn)
        self.save(cfile, content, "wb")
        return ufn

    def store_statement(self, collection, id, statement):
        """ Store the supplied statement document content in the object idenfied by the id in the specified collection """
        # store the RDF version
        sfile = os.path.join(self.configuration.store_dir, collection, id, "sss_statement.xml")
        self.save(sfile, statement.serialise())
        # store the Atom Feed version
        sfile = os.path.join(self.configuration.store_dir, collection, id, "sss_statement.atom.xml")
        self.save(sfile, statement.serialise_atom())

    def store_deposit_receipt(self, collection, id, receipt):
        """ Store the supplied receipt document content in the object idenfied by the id in the specified collection """
        drfile = os.path.join(self.configuration.store_dir, collection, id, "sss_deposit-receipt.xml")
        if not isinstance(receipt, str):
            receipt = etree.tostring(receipt, pretty_print=True)
        self.save(drfile, receipt)

    def store_metadata(self, collection, id, metadata):
        """ Store the supplied metadata dictionary in the object idenfied by the id in the specified collection """
        md = etree.Element(self.ns.DC + "metadata", nsmap=self.mdmap)
        for dct in metadata.keys():
            for v in metadata[dct]:
                element = etree.SubElement(md, self.ns.DC + dct)
                element.text = v
        s = etree.tostring(md, pretty_print=True)
        mfile = os.path.join(self.configuration.store_dir, collection, id, "sss_metadata.xml")
        self.save(mfile, s)

    def get_metadata(self, collection, id):
        if not self.file_exists(collection, id, "sss_metadata.xml"):
            return {}
        mfile = os.path.join(self.configuration.store_dir, collection, id, "sss_metadata.xml")
        f = open(mfile, "r")
        metadata = etree.fromstring(f.read())
        md = {}
        for dc in metadata.getchildren():
            tag = dc.tag
            if tag.startswith(self.ns.DC):
                tag = tag[len(self.ns.DC):]
            if md.has_key(tag):
                md[tag].append(dc.text.strip())
            else:
                md[tag] = [dc.text.strip()]
        return md

    def remove_content(self, collection, id, keep_metadata=False, keep_atom=False):
        """
        Remove all the content from the specified container.  If keep_metadata is True then the sss_metadata.xml
        file will not be removed
        """
        odir = os.path.join(self.configuration.store_dir, collection, id)
        for file in os.listdir(odir):
            # if there is a metadata.xml but metadata suppression on the deposit is turned on
            # then leave it alone
            if file == "sss_metadata.xml" and keep_metadata:
                continue
            if file == "atom.xml" and keep_atom:
                continue
            dpath = os.path.join(odir, file)
            os.remove(dpath)

    def remove_container(self, collection, id):
        """ Remove the specified container and all of its contents """

        # first remove the contents of the container
        self.remove_content(collection, id)

        # finally remove the container itself
        odir = os.path.join(self.configuration.store_dir, collection, id)
        os.rmdir(odir)

    def get_store_path(self, collection, id=None, filename=None):
        """
        Get the path to the specified filename in the store.  This is a utility method and should be used with care;
        all content which goes into the store through the store_content method will have its filename localised to
        avoid name clashes, so this method CANNOT be used to retrieve those files.  Instead, this should be used
        internally to locate sss specific files in the container, and for packagers to write their own files into
        the store which are not part of the content itself.
        """
        if filename is not None:
            return os.path.join(self.configuration.store_dir, collection, id, filename)
        if id is not None:
            return os.path.join(self.configuration.store_dir, collection, id)
        return os.path.join(self.configuration.store_dir, collection)

    def get_deposit_receipt_content(self, collection, id):
        """ Read the deposit receipt for the specified container """
        f = open(self.get_store_path(collection, id, "sss_deposit-receipt.xml"), "r")
        return f.read()

    def get_statement_content(self, collection, id):
        """ Read the statement for the specified container """
        f = open(self.get_store_path(collection, id, "sss_statement.xml"), "r")
        return f.read()

    def get_statement_feed(self, collection, id):
        """ Read the statement for the specified container """
        f = open(self.get_store_path(collection, id, "sss_statement.atom.xml"), "r")
        return f.read()

    def get_atom_content(self, collection, id):
        """ Read the statement for the specified container """
        if not self.file_exists(collection, id, "atom.xml"):
            return None
        f = open(self.get_store_path(collection, id, "atom.xml"), "r")
        return f.read()

    def load_statement(self, collection, id):
        """
        Load the Statement object for the specified container
        Returns a Statement object fully populated to represent this object
        """
        sfile = os.path.join(self.configuration.store_dir, collection, id, "sss_statement.xml")
        s = Statement()
        s.load(sfile)
        return s

    def list_content(self, collection, id, exclude=[]):
        """
        List the contents of the specified container, excluding any files whose name exactly matches those in the
        exclude list.  This method will also not list sss specific files, thus limiting it to the content files of
        the object.
        """
        cdir = os.path.join(self.configuration.store_dir, collection)
        odir = os.path.join(cdir, id)
        cfiles = [f for f in os.listdir(odir) if not f.startswith("sss_") and not f in exclude]
        return cfiles

# DISSEMINATION PACKAGING
#######################################################################
# This section contains a Packager interface and classes which provide dissemination packaging for the SSS
# Packagers can be configured in the Configuration object to be called for requested content types

class DisseminationPackager(object):
    """
    Interface for all classes wishing to provide dissemination packaging services to the SSS
    """
    def package(self, collection, id):
        """
        Package up all the content in the specified container.  This method must be implemented by the extender.  The
        method should create a package in the store directory, and then return to the caller the path to that file
        so that it can be served back to the client
        """
        pass
        
    def get_uri(self):
        return "http://purl.org/net/sword/package/SimpleZip"

class DefaultDisseminator(DisseminationPackager):
    """
    Basic default packager, this just zips up everything except the SSS specific files in the container and stores
    them in a file called sword-default-package.zip.
    """
    def __init__(self):
        self.dao = DAO()

    def package(self, collection, id):
        """ package up the content """

        # get a list of the relevant content files
        files = self.dao.list_content(collection, id, exclude=["sword-default-package.zip"])

        # create a zip file with all the original zip files in it
        zpath = self.dao.get_store_path(collection, id, "sword-default-package.zip")
        z = ZipFile(zpath, "w")
        for file in files:
            z.write(self.dao.get_store_path(collection, id, file), file)
        z.close()

        # return the path to the package to the caller
        return zpath

class FeedDisseminator(DisseminationPackager):
    def __init__(self):
        self.dao = DAO()
        self.ns = Namespaces()
        self.um = URIManager()
        self.nsmap = {None: self.ns.ATOM_NS}

    def package(self, collection, id):
        """ create a feed representation of the package """
        # get a list of the relevant content files
        files = self.dao.list_content(collection, id, exclude=["mediaresource.feed.xml"])

        # create a feed object with all the files as entries
        feed = etree.Element(self.ns.ATOM + "feed", nsmap=self.nsmap)
        
        for file in files:
            entry = etree.SubElement(feed, self.ns.ATOM + "entry")
            
            em = etree.SubElement(entry, self.ns.ATOM + "link")
            em.set("rel", "edit-media")
            em.set("href", self.um.part_uri(collection, id, file))
            
            edit = etree.SubElement(entry, self.ns.ATOM + "link")
            edit.set("rel", "edit")
            edit.set("href", self.um.part_uri(collection, id, file) + ".atom")
            
            content = etree.SubElement(entry, self.ns.ATOM + "link")
            content.set("type", "application/octet-stream") # FIXME: we're not storing content types, so we don't know
            content.set("src", self.um.part_uri(collection, id, file))
        
        fpath = self.dao.get_store_path(collection, id, "mediaresource.feed.xml")
        f = open(fpath, "wb")
        f.write(etree.tostring(feed, pretty_print=True))
        f.close()
        
        return fpath
        
    def get_uri(self):
        return None

class IngestPackager(object):
    def ingest(self, collection, id, filename, metadata_relevant):
        """
        The package with the supplied filename has been placed in the identified container.  This should be inspected
        and unpackaged.  Implementations should note that there is optionally an atom document in the container which
        may need to be inspected, and this can be retrieved from DAO.get_atom_content().  If the metadata_relevant
        argument is False, implementations should not change the already extracted metadata in the container
        """
        return []

class BinaryIngester(IngestPackager):
    def ingest(self, collection, id, filename, metadata_relevant):
        # does nothing, we don't try to unpack binary deposits
        return []

class SimpleZipIngester(IngestPackager):
    def __init__(self):
        self.dao = DAO()
        self.ns = Namespaces()
        
    def ingest(self, collection, id, filename, metadata_relevant=True):
        # First, let's just extract all the contents of the zip
        z = ZipFile(self.dao.get_store_path(collection, id, filename))
        
        # keep track of the names of the files in the zip, as these will become
        # our derived resources
        derived_resources = z.namelist()
        
        # FIXME: what we do here is intrinsically insecure, but SSS is not a
        # production service, so we're not worrying about it!
        path = self.dao.get_store_path(collection, id)
        z.extractall(path)
        
        # check for the atom document
        atom = self.dao.get_atom_content(collection, id)
        if atom is None:
            # there's no metadata to extract so just leave it
            return derived_resources

        # if the metadata is not relevant, then we don't need to continue
        if not metadata_relevant:
            return derived_resources
            
        metadata = {}
        entry = etree.fromstring(atom)

        # go through each element in the atom entry and just process the ones we care about
        # explicitly retrieve the atom based metadata first
        for element in entry.getchildren():
            if element.tag == self.ns.ATOM + "title":
                self.a_insert(metadata, "title", element.text.strip())
            if element.tag == self.ns.ATOM + "updated":
                self.a_insert(metadata, "date", element.text.strip())
            if element.tag == self.ns.ATOM + "author":
                authors = ""
                for names in element.getchildren():
                    authors += names.text.strip() + " "
                self.a_insert(metadata, "creator", authors.strip())
            if element.tag == self.ns.ATOM + "summary":
                self.a_insert(metadata, "abstract", element.text.strip())

        # now go through and retrieve the dcterms from the entry
        for element in entry.getchildren():
            if not isinstance(element.tag, basestring):
                continue
                
            # we operate an additive policy with metadata.  Duplicate
            # keys are allowed, but duplicate key/value pairs are not.
            if element.tag.startswith(self.ns.DC):
                key = element.tag[len(self.ns.DC):]
                val = element.text.strip()
                self.a_insert(metadata, key, val)

        self.dao.store_metadata(collection, id, metadata)
        
        return derived_resources
        
    def a_insert(self, d, key, value):
        if d.has_key(key):
            vs = d[key]
            if value not in vs:
                d[key].append(value)
        else:
            d[key] = [value]

class METSDSpaceIngester(IngestPackager):
    def ingest(self, collection, id, filename, metadata_relevant):
        # we don't need to implement this, it is just for example.  it would unzip the file and import the metadata
        # in the zip file
        return []

class DefaultEntryIngester(object):
    def __init__(self):
        self.dao = DAO()
        self.ns = Namespaces()
        
    def ingest(self, collection, id, atom, additive=False):
        ssslog.debug("Ingesting Metadata; Additive? " + str(additive))
        
        # store the atom
        self.dao.store_atom(collection, id, atom)
        
        # now extract/augment the metadata
        metadata = {}
        if additive:
            # start with any existing metadata
            metadata = self.dao.get_metadata(collection, id)
        
        ssslog.debug("Existing Metadata (before new ingest): " + str(metadata))
        
        entry = etree.fromstring(atom)

        # go through each element in the atom entry and just process the ones we care about
        # explicitly retrieve the atom based metadata first
        for element in entry.getchildren():
            if element.tag == self.ns.ATOM + "title":
                self.a_insert(metadata, "title", element.text.strip())
            if element.tag == self.ns.ATOM + "updated":
                self.a_insert(metadata, "date", element.text.strip())
            if element.tag == self.ns.ATOM + "author":
                authors = ""
                for names in element.getchildren():
                    authors += names.text.strip() + " "
                self.a_insert(metadata, "creator", authors.strip())
            if element.tag == self.ns.ATOM + "summary":
                self.a_insert(metadata, "abstract", element.text.strip())

        # now go through and retrieve the dcterms from the entry
        for element in entry.getchildren():
            if not isinstance(element.tag, basestring):
                continue
                
            # we operate an additive policy with metadata.  Duplicate
            # keys are allowed, but duplicate key/value pairs are not.
            if element.tag.startswith(self.ns.DC):
                key = element.tag[len(self.ns.DC):]
                val = element.text.strip()
                self.a_insert(metadata, key, val)

        ssslog.debug("Current Metadata (extracted + previously existing): " + str(metadata))

        self.dao.store_metadata(collection, id, metadata)

    def a_insert(self, d, key, value):
        if d.has_key(key):
            vs = d[key]
            if value not in vs:
                d[key].append(value)
        else:
            d[key] = [value]

# Basic Web Interface
#######################################################################

class WebPage(object):
    def _wrap_html(self, title, frag, head_frag=None):
        return "<html><head><title>" + title + "</title>" + head_frag + "</head><body>" + frag + "</body></html>"

class HomePage(WebPage):
    """
    Welcome / home page
    """
    def __init__(self):
        self.dao = DAO()
        self.um = URIManager()
        
    def get_home_page(self):
        cfg = global_configuration
        
        frag = "<h1>Simple SWORDv2 Server</h1>"
        frag += "<p><strong>Service Document (SD-IRI)</strong>: <a href=\"" + cfg.base_url + "sd-uri\">" + cfg.base_url + "sd-uri</a></p>"
        frag += "<p>If prompted, use the username <strong>" + cfg.user + "</strong> and the password <strong>" + cfg.password + "</strong></p>"
        frag += "<p>The On-Behalf-Of user to use is <strong>" + cfg.obo + "</strong></p>"
        
        # list the collections
        frag += "<h2>Collections</h2><ul>"
        for col in self.dao.get_collection_names():
            frag += "<li><a href=\"" + self.um.html_url(col) + "\">" + col + "</a></li>"
        frag += "</ul>"
        
        head_frag = "<link rel=\"http://purl.org/net/sword/discovery/service-document\" href=\"" + cfg.base_url + "sd-uri\"/>"
        
        return self._wrap_html("Simple SWORDv2 Server", frag, head_frag)

class CollectionPage(WebPage):
    def __init__(self):
        self.dao = DAO()
        self.um = URIManager()
        
    def get_collection_page(self, id):
        frag = "<h1>Collection: " + id + "</h1>"
        
        # list all of the containers in the collection
        cpath = self.dao.get_store_path(id)
        containers = os.listdir(cpath)
        frag += "<h2>Containers</h2><ul>"
        for container in containers:
            frag += "<li><a href=\"" + self.um.html_url(id, container) + "\">" + container + "</a></li>"
        frag += "</ul>"
        
        head_frag = "<link rel=\"http://purl.org/net/sword/terms/deposit\" href=\"" + self.um.col_uri(id) + "\"/>"
        
        return self._wrap_html("Collection: " + id, frag, head_frag)

class ItemPage(WebPage):
    def __init__(self):
        self.dao = DAO()
        self.um = URIManager()
    
    def get_item_page(self, oid):
        collection, id = self.um.interpret_oid(oid)
        statement = self.dao.load_statement(collection, id)
        metadata = self.dao.get_metadata(collection, id)
        
        state_frag = self._get_state_frag(statement)
        md_frag = self._layout_metadata(metadata)
        file_frag = self._layout_files(statement)
        
        frag = "<h1>Item: " + id + "</h1>"
        frag += "<strong>State</strong>: " + state_frag
        frag += self._layout_sections(md_frag, file_frag)
        
        head_frag = "<link rel=\"http://purl.org/net/sword/terms/edit\" href=\"" + self.um.edit_uri(collection, id) + "\"/>"
        head_frag += "<link rel=\"http://purl.org/net/sword/terms/statement\" href=\"" + self.um.state_uri(collection, id, "atom") + "\"/>"
        head_frag += "<link rel=\"http://purl.org/net/sword/terms/statement\" href=\"" + self.um.state_uri(collection, id, "ore") + "\"/>"
        
        return self._wrap_html("Item: " + id, frag, head_frag)
    
    def _layout_metadata(self, metadata):
        frag = "<h2>Metadata</h2>"
        for key, vals in metadata.iteritems():
            frag += "<strong>" + key + "</strong>: " + ", ".join(vals) + "<br/>"
        if len(metadata) == 0:
            frag += "No metadata associated with this item"
        return frag
        
    def _layout_files(self, statement):
        frag = "<h2>Files</h2>"
        frag += "<table border=\"1\"><tr><th>URI</th><th>deposited on</th><th>format</th><th>deposited by</th><th>on behalf of</th></tr>"
        for uri, deposit_time, format, by, obo in statement.original_deposits:
            frag += "<tr><td><a href=\"" + uri + "\">" + uri + "</a></td><td>" + str(deposit_time) + "</td><td>" + format
            frag += "</td><td>" + by + "</td><td>" + str(obo) + "</td></tr>"
        frag += "</table>"
        return frag
    
    def _get_state_frag(self, statement):
        if statement.in_progress:
            return statement.in_progress_uri
        else:
            return statement.archived_uri
    
    def _layout_sections(self, metadata, files):
        return "<table border=\"0\"><tr><td valign=\"top\">" + metadata + "</td><td valign=\"top\">" + files + "</td></tr></table>"

# WEB SERVER
#######################################################################
# This is the bit which actually invokes the web.py server when this module is run

# create the global configuration
global_configuration = CherryPyConfiguration()

# get the global logger
sssl = SSSLogger()
ssslog = sssl.getLogger()

# if we run the file as a mod_wsgi module, do this
application = web.application(urls, globals()).wsgifunc()

# if we run the file directly, use the bundled CherryPy server ...
if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()
