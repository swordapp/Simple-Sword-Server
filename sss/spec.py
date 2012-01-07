# FIXME: this covers a lot of constants, so we should consider getting rid of
# all these extraneous objects and just have dictionaries which can be imported

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
        
class Errors(object):
    content = "http://purl.org/net/sword/error/ErrorContent"
    checksum_mismatch = "http://purl.org/net/sword/error/ErrorChecksumMismatch"
    bad_request = "http://purl.org/net/sword/error/ErrorBadRequest"
    target_owner = "http://purl.org/net/sword/error/TargetOwnerUnknown"
    mediation_not = "http://purl.org/net/sword/error/MediationNotAllowed"
    method_not_allowed = "http://purl.org/net/sword/error/MethodNotAllowed"
    max_upload_size_exceeded = "http://purl.org/net/sword/error/MaxUploadSizeExceeded"


