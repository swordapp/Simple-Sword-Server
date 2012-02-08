import os, uuid, sys, json
from ingesters_disseminators import DefaultEntryIngester, DefaultDisseminator, FeedDisseminator, BinaryIngester, SimpleZipIngester, METSDSpaceIngester
from negotiator import AcceptParameters, ContentType
from core import SwordServer, Authenticator, WebUI

from sss_logging import logging
ssslog = logging.getLogger(__name__)

SSS_CONFIG_FILE = "./sss.conf.json"

DEFAULT_CONFIG = """
{
    ############################################################################
    # SWORD SERVER CONFIGURATION
    ############################################################################
    # This configuration file specifies the parameters for SSS
    #
    # Each configuration option can be accessed as an attribute of the 
    # Configuration python object.  e.g.
    #
    #   Configuration().base_url
    #
    # You may add any other configuration options directly to this JSON file
    # and they will be picked up in the same way by the Configuration object.
    #
    # Some core configuration options have special methods for access built into
    # the Configuration object (check the docs for details)
    #
    # This file is JSON formatted with one extension: comments are allowed.
    # Comments are must be on a line of their own, and prefixed with #.  The #
    # must be the first non-whitespace character on the line.  The configuration
    # interpreter will strip all such lines before parsing the JSON, but will
    # leave blank lines in the resulting JSON so that errors may be detected
    # accurately by line number.
    #
    # To validate an this file, run:
    #
    #   python config.py /path/to/sss.conf.json
    #
    ############################################################################
    
    # The base url of the webservice where SSS is deployed
    "base_url" : "http://localhost:8080/",
    # if you are using Apache, you should probably use this base_url instead
    # "base_url" : "http://localhost/sss/",
    
    # The number of collections that SSS will create and give to users to deposit content into
    "num_collections" : 10,
    
    # The directory where the deposited content should be stored
    "store_dir" : "./store/",
    # If you are using Apache you should set the store directory in full
    
    # explicitly set the sword version, so if you're testing validation of
    # service documents you can "break" it.
    "sword_version" : "2.0",
    
    # user details; the user/password pair should be used for HTTP Basic Authentication, and the obo is the user
    # to use for On-Behalf-Of requests.  Set authenticate=False if you want to test the server without caring
    # about authentication, set mediation=False if you want to test the server's errors on invalid attempts at
    # mediation
    "authenticate" : true,
    # If you are using apache, you can turn off this authentication and leave it
    # to the standard apache auth module
    # "authenticate" : false,
    "user" : "sword",
    "password" : "sword",
    
    "mediation" : true,
    "obo" : "obo",
    
    # What media ranges should the app:accept element in the Service Document support
    "app_accept" : [ "*/*" ],
    "multipart_accept" : [ "*/*" ],
    "accept_nothing" : false,
    
    # use these app_accept and multipart_accept values to create an invalid Service Document
    # "app_accept" : null,
    # "multipart_accept" : null,
    
    # should we provide sub-service urls
    "use_sub" : true,
    
    # What packaging formats should the sword:acceptPackaging element in the Service Document support
    "sword_accept_package" : [
            "http://purl.org/net/sword/package/SimpleZip",
            "http://purl.org/net/sword/package/Binary",
            "http://purl.org/net/sword/package/METSDSpaceSIP"
        ],
    
    # maximum upload size to be allowed, in bytes (this default is 16Mb)
    "max_upload_size" : 16777216,
    # used to generate errors
    # "max_upload_size" : 0,
    # Just omit the max_upload_size parameter if you don't want any limit
    
    # list of package formats that SSS can provide when retrieving the Media Resource
    "sword_disseminate_package" : [
        "http://purl.org/net/sword/package/SimpleZip"
    ],
    
    
    # Supported package format disseminators; for the content type (dictionary key), the associated
    # class will be used to package the content for dissemination
    "package_disseminators" : {
            "(& (type=\\"application/zip\\") (packaging=\\"http://purl.org/net/sword/package/SimpleZip\\") )" : "sss.ingesters_disseminators.DefaultDisseminator",
            "(& (type=\\"application/zip\\") )" : "sss.ingesters_disseminators.DefaultDisseminator",
            "(& (type=\\"application/atom+xml;type=feed\\") )" : "sss.ingesters_disseminators.FeedDisseminator"
    },
    
    # Supported package format ingesters; for the Packaging header (dictionary key), the associated class will
    # be used to unpackage deposited content
    "package_ingesters" : {
            "http://purl.org/net/sword/package/Binary" : "sss.ingesters_disseminators.BinaryIngester",
            "http://purl.org/net/sword/package/SimpleZip" : "sss.ingesters_disseminators.SimpleZipIngester",
            "http://purl.org/net/sword/package/METSDSpaceSIP" : "sss.ingesters_disseminators.METSDSpaceIngester"
    },
    
    # Ingester to use for atom entries
    "entry_ingester" : "sss.ingesters_disseminators.DefaultEntryIngester",
    
    # supply this header in the Packaging header to generate a http://purl.org/net/sword/error/ErrorContent
    # sword error
    "error_content_package" : "http://purl.org/net/sword/package/error",
    
    # we can turn off updates and deletes in order to examine the behaviour of Method Not Allowed errors
    "allow_update" : true,
    "allow_delete" : true,
    
    # we can turn off deposit receipts, which is allowed by the specification
    "return_deposit_receipt" : true,

    # The acceptable formats that the server can return the media resource in
    # on request.
    # This is used in Content Negotiation during GET on the EM-URI
    "media_resource_formats" : [
        {"content_type" : "application/zip", "packaging": "http://purl.org/net/sword/package/SimpleZip"},
        {"content_type" : "application/zip"},
        {"content_type" : "application/atom+xml;type=feed"},
        {"content_type" : "text/html"}
    ],
    
    # If no Accept parameters are given to the server on GET to the EM-URI the
    # following defaults will be used to determine the response type
    "media_resource_default" : {
        "content_type" : "application/zip"
    },
    
    # The acceptable formats that the server can return the entry document in
    # on request
    # This is used in Content Negotiation during GET on the Edit-URI
    "container_formats" : [
        {"content_type" : "application/atom+xml;type=entry" },
        {"content_type" : "application/atom+xml;type=feed" },
        {"content_type" : "application/rdf+xml" }
    ],
    
    # If no Accept parameters are given to the server on GET to the Edit-URI the
    # following defaults will be used to determine the response type
    "container_format_default" : {
        "content_type" : "application/atom+xml;type=entry"
    },
    
    # Dynamically load the implementation classes for the 3 main interfaces
    # In this default configuration we use the built-in SSS repository's 
    # implementations for everything
    "sword_server" : "sss.repository.SSS",
    "authenticator" : "sss.repository.SSSAuthenticator",
    "webui" : "sss.repository.WebInterface"
}
"""
        
class Configuration(object):
    def __init__(self, config_file=None):
        self.SSS_CONFIG_FILE = SSS_CONFIG_FILE  # default
        if config_file is not None:
            self.SSS_CONFIG_FILE = config_file
        
        # extract the configuration from the json object
        self.cfg = self._load_json()
        
        # FIXME: we might need to do some work on these:
        # self.base_url = "http://localhost:%s/" % (sys.argv[1] if len(sys.argv) > 1 else '8080')
        # self.store_dir = os.path.join(os.getcwd(), "store")
        # at the moment they are just set in the configuration as strings, and
        # it's a bit of a faff to include the code that was there before into
        # the json string.  How much does this matter?
    
    def get_server_implementation(self):
        if self.sword_server is not None:
            return self._get_class(self.sword_server)
        else:
            return SwordServer
    
    def get_authenticator_implementation(self):
        if self.authenticator is not None:
            return self._get_class(self.authenticator)
        else:
            return Authenticator
        
    def get_webui_implementation(self):
        if self.webui is not None:
            return self._get_class(self.webui)
        else:
            return WebUI
    
    def get_container_formats(self):
        default_params = self._get_accept_params(self.container_format_default)
        
        acceptable = []
        for format in self.container_formats:
            acceptable.append(self._get_accept_params(format))
        
        return default_params, acceptable
    
    def get_media_resource_formats(self):
        default_params = self._get_accept_params(self.media_resource_default)
        
        acceptable = []
        for format in self.media_resource_formats:
            acceptable.append(self._get_accept_params(format))
        
        return default_params, acceptable
        
    def _get_accept_params(self, obj):
        params = AcceptParameters()
        for k, v in obj.items():
            if k == "content_type":
                params.content_type = ContentType(v)
            elif k == "packaging":
                params.packaging = v
        return params
    
    def get_package_disseminator(self, media_format):
        path = self.package_disseminators.get(media_format)
        return self._get_class(path)
        
    def get_package_ingester(self, package):
        path = self.package_ingesters.get(package)
        ssslog.debug("loading class from " + str(path))
        return self._get_class(path)
    
    def get_entry_ingester(self):
        return self._get_class(self.entry_ingester)
    
    def _get_class(self, path):
        if path is None:
            return None
        
        # split out the classname and the modpath
        components = path.split(".")
        classname = components[-1:][0]
        modpath = ".".join(components[:-1])
        
        return self._load_class(modpath, classname)
    
    def _load_class(self, modpath, classname):
        # now, do some introspection to get a handle on the class
        try:
            mod = __import__(modpath, fromlist=[classname])
            klazz = getattr(mod, classname)
            return klazz
        except ImportError as e:
            # in this case it's possible that it's just a context thing, and
            # the class we're trying to load is in /this/ package, and therefore
            # can't be reference with sss as the top level module.  If that's
            # the case then we can try again
            ssslog.debug("ImportError thrown loading class: " + classname + " from module " + modpath)
            if modpath.startswith("sss."):
                ssslog.debug("Module path " + modpath + " starts with 'sss' so ImportError may be due to module path context; trying without 'sss'")
                modpath = modpath[4:]
                return self._load_class(modpath, classname)
            else:
                raise e
        except AttributeError as e:
            ssslog.debug("Tried and failed to load " + classname + " from " + modpath)
            raise e
    
    def _load_json(self):
        if not os.path.isfile(self.SSS_CONFIG_FILE):
            self._create_config_file()
        
        f = open(self.SSS_CONFIG_FILE)
        c = ""
        for line in f:
            if line.strip().startswith("#"):
                c+= "\n" # this makes it easier to debug the config
            else:
                c += line
        return json.loads(c)
    
    def _create_config_file(self):
        fn = open(self.SSS_CONFIG_FILE, "w")
        fn.write(DEFAULT_CONFIG)
        fn.close()
    
    def __getattr__(self, attr):
        return self.cfg.get(attr, None)
        
if __name__ == "__main__":
    # if we are run from the command line, run validation over the
    # specified file
    if len(sys.argv) != 2:
        print "Please supply a path to a file to validate"
        exit()
    print "Validating Configuration File: " + sys.argv[1]
    c = Configuration(config_file=sys.argv[1])
    print "File is valid"
