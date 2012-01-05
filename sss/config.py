import os, uuid, sys
from negotiator import ContentType
from ingesters_disseminators import DefaultEntryIngester, DefaultDisseminator, FeedDisseminator, BinaryIngester, SimpleZipIngester, METSDSpaceIngester

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
