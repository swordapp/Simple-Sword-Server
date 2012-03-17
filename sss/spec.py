# FIXME: this covers a lot of constants, so we should consider getting rid of
# all these extraneous objects and just have dictionaries which can be imported

from sss_logging import logging
ssslog = logging.getLogger(__name__)

# FIXME: this is a poorly constructed object
class Namespaces(object):
    """
    This class encapsulates all the namespace declarations that we will need
    """
    def __init__(self):
        # AtomPub namespace and lxml format
        self.APP_NS = "http://www.w3.org/2007/app"
        self.APP = "{%s}" % self.APP_NS
        self.APP_PREFIX = "app"

        # Atom namespace and lxml format
        self.ATOM_NS = "http://www.w3.org/2005/Atom"
        self.ATOM = "{%s}" % self.ATOM_NS
        self.ATOM_PREFIX = "atom"

        # SWORD namespace and lxml format
        self.SWORD_NS = "http://purl.org/net/sword/terms/"
        self.SWORD = "{%s}" % self.SWORD_NS
        self.SWORD_PREFIX = "sword"
        
        # SWORD State Scheme
        self.SWORD_STATE = self.SWORD_NS + "state"

        # Dublin Core namespace and lxml format
        self.DC_NS = "http://purl.org/dc/terms/"
        self.DC = "{%s}" % self.DC_NS
        self.DC_PREFIX = "dcterms"

        # RDF namespace and lxml format
        self.RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        self.RDF = "{%s}" % self.RDF_NS
        self.RDF_PREFIX = "rdf"

        # ORE namespace and lxml format
        self.ORE_NS = "http://www.openarchives.org/ore/terms/"
        self.ORE = "{%s}" % self.ORE_NS
        self.ORE_PREFIX = "ore"

        # ORE ATOM
        self.ORE_ATOM_NS = "http://www.openarchives.org/ore/atom/"
        self.ORE_ATOM = "{%s}" % self.ORE_ATOM_NS
        self.ORE_ATOM_PREFIX = "oreatom"
        
        # lookup dictionary
        self.prefix = {
            self.APP_NS : self.APP_PREFIX,
            self.ATOM_NS : self.ATOM_PREFIX,
            self.SWORD_NS : self.SWORD_PREFIX,
            self.DC_NS : self.DC_PREFIX,
            self.RDF_NS : self.RDF_PREFIX,
            self.ORE_NS : self.ORE_PREFIX,
            self.ORE_ATOM_NS : self.ORE_ATOM_PREFIX
        }
        
class Errors(object):
    content = "http://purl.org/net/sword/error/ErrorContent"
    checksum_mismatch = "http://purl.org/net/sword/error/ErrorChecksumMismatch"
    bad_request = "http://purl.org/net/sword/error/ErrorBadRequest"
    target_owner_unknown = "http://purl.org/net/sword/error/TargetOwnerUnknown"
    mediation_not_allowed = "http://purl.org/net/sword/error/MediationNotAllowed"
    method_not_allowed = "http://purl.org/net/sword/error/MethodNotAllowed"
    max_upload_size_exceeded = "http://purl.org/net/sword/error/MaxUploadSizeExceeded"
    
    statuses = {
        content : 415,
        checksum_mismatch: 412,
        bad_request: 400,
        target_owner_unknown: 403,
        mediation_not_allowed : 412,
        method_not_allowed: 405,
        max_upload_size_exceeded: 413
    }
    
    def get_status(self, uri):
        status = Errors.statuses.get(uri)
        return status if status is not None else 400

class ValidationException(Exception):
    def __init__(self, message):
        self.message = message

class HttpHeaders(object):
    content_type = "content-type"
    content_disposition = "content-disposition"
    content_md5 = "content-md5"
    packaging = "packaging"
    in_progress = "in-progress"
    on_behalf_of = "on-behalf-of"
    metadata_relevant = "metadata-relevant"
    slug = "slug"
    content_length = "content-length"
    
    sword_headers = {
        content_type : None,
        content_md5: None,
        packaging : "http://purl.org/net/sword/package/Binary",
        in_progress : "false",
        on_behalf_of : None,
        metadata_relevant : "true",
        slug : None,
        content_length : 0
    }
    
    allowed_values = {
        in_progress.lower() : ["true", "false"],
        metadata_relevant.lower() : ["true", "false"]
    }
    
    spec_compliance = {
        "6.3.1" : [
            (content_type.lower(), "SHOULD"),
            (content_disposition.lower(), "MUST"),
            (content_md5.lower(), "SHOULD"),
            (packaging.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY"),
            (slug.lower(), "MAY")
        ], 
        "6.3.2" : [
            (content_type.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY"),
            (slug.lower(), "MAY")
        ],
        "6.3.3" : [
            (content_type.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY"),
            (slug.lower(), "MAY")
        ],
        "6.5.1" : [
            (content_type.lower(), "SHOULD"),
            (content_disposition.lower(), "MUST"),
            (content_md5.lower(), "SHOULD"),
            (packaging.lower(), "SHOULD"),
            (on_behalf_of.lower(), "MAY"),
            (metadata_relevant.lower(), "MAY")
        ],
        "6.5.2" : [
            (content_type.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY")
        ],
        "6.5.3" : [
            (content_type.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY")
        ],
        "6.6" : [
            (on_behalf_of.lower(), "MAY"),
        ],
        "6.7.1" : [
            (content_type.lower(), "SHOULD"),
            (content_disposition.lower(), "MUST"),
            (content_md5.lower(), "SHOULD"),
            (packaging.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY"),
            (slug.lower(), "MAY")
        ],
        "6.7.2" : [
            (content_type.lower(), "MUST"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY")
        ],
        "6.7.3" : [
            (content_type.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY"),
            (metadata_relevant.lower(), "MAY")
        ],
        "6.8" : [
            (on_behalf_of.lower(), "MAY"),
        ],
        "9.3" : [
            (content_length.lower(), "SHOULD"),
            (in_progress.lower(), "MAY"),
            (on_behalf_of.lower(), "MAY"),
        ]
    }
    
    def is_allowed_value(self, header, value):
        header = header.lower()
        if HttpHeaders.allowed_values.has_key(header):
            if value.lower() in HttpHeaders.allowed_values[header]:
                return True
            else:
                return False
        return True
        
    def get_allowed_values(self, header):
        if HttpHeaders.allowed_values.has_key(header):
            return HttpHeaders.allowed_values[header]
        return []
        
    def validate(self, header_dict, section):
        ssslog.info("Validating under requirements from SWORD spec section " + section)
        normalised_dict = dict([(h.lower(), v) for h, v in header_dict.items()])
        ssslog.debug("Normalised header dictionary: " + str(normalised_dict))
        spec_compliance = HttpHeaders.spec_compliance.get(section, [])
        for header, requirement in spec_compliance:
            ssslog.debug("Looking for " + header + " with requirement " + requirement)
            value = normalised_dict.get(header)
            if value is not None and not self.is_allowed_value(header, value):
                ssslog.error(header + " had value (" + value + "), which is not an allowed value")
                raise ValidationException(value + " is not an allowed value of " + header)
            if value is None and requirement == "MUST":
                ssslog.error(header + " MUST be supplied, but is missing or empty")
                raise ValidationException(header + " MUST be supplied, but is missing or empty")

    def get_sword_headers(self, header_dict):
        normalised_dict = dict([(h.lower(), v) for h, v in header_dict.items()])
        headers = {}
        for head, value in normalised_dict.items():
            # is it a sword header
            if HttpHeaders.sword_headers.has_key(head):
                headers[head] = value
        for head, default in HttpHeaders.sword_headers.items():
            if head not in headers.keys():
                headers[head] = default
        return headers
        
    def extract_filename(self, header_dict):
        normalised_dict = dict([(h.lower(), v) for h, v in header_dict.items()])
        """ get the filename out of the content disposition header """
        cd = normalised_dict.get(HttpHeaders.content_disposition)
        if cd is not None:
            ssslog.debug("Extracting filename from " + HttpHeaders.content_disposition + " " + str(cd))
            # ok, this is a bit obtuse, but it was fun making it.  It's not hard to understand really, if you break
            # it down
            return cd[cd.find("filename=") + len("filename="):cd.find(";", cd.find("filename=")) if cd.find(";", cd.find("filename=")) > -1 else len(cd)]
        else:
            return None













