import web, os, base64
from lxml import etree
from datetime import datetime
from spec import Namespaces, HttpHeaders, Errors
from info import __version__

from sss_logging import logging
ssslog = logging.getLogger(__name__)

class SwordServer(object):
    """
    The main SWORD Server class.  This class deals with all the CRUD requests as provided by the web.py HTTP
    handlers
    """
    def __init__(self, config, auth):
        # get the configuration
        self.configuration = config
        self.auth_credentials = auth

    def container_exists(self, path):
        raise NotImplementedError()

    def media_resource_exists(self, path):
        raise NotImplementedError()

    def service_document(self, path=None):
        """
        Construct the Service Document.  This takes the set of collections that are in the store, and places them in
        an Atom Service document as the individual entries
        """
        raise NotImplementedError()

    def list_collection(self, path):
        """
        List the contents of a collection identified by the supplied id
        """
        raise NotImplementedError()

    def deposit_new(self, path, deposit):
        """
        Take the supplied deposit and treat it as a new container with content to be created in the specified collection
        Args:
        -collection:    the ID of the collection to be deposited into
        -deposit:       the DepositRequest object to be processed
        Returns a DepositResponse object which will contain the Deposit Receipt or a SWORD Error
        """
        raise NotImplementedError()

    def get_media_resource(self, path, accept_parameters):
        """
        Get a representation of the media resource for the given id as represented by the specified content type
        -id:    The ID of the object in the store
        -content_type   A ContentType object describing the type of the object to be retrieved
        """
        raise NotImplementedError()
    
    def replace(self, path, deposit):
        """
        Replace all the content represented by the supplied id with the supplied deposit
        Args:
        - oid:  the object ID in the store
        - deposit:  a DepositRequest object
        Return a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        raise NotImplementedError()

    def delete_content(self, path, delete):
        """
        Delete all of the content from the object identified by the supplied id.  the parameters of the delete
        request must also be supplied
        - oid:  The ID of the object to delete the contents of
        - delete:   The DeleteRequest object
        Return a DeleteResponse containing the Deposit Receipt or the SWORD Error
        """
        raise NotImplementedError()
        
    def add_content(self, path, deposit):
        """
        Take the supplied deposit and treat it as a new container with content to be created in the specified collection
        Args:
        -collection:    the ID of the collection to be deposited into
        -deposit:       the DepositRequest object to be processed
        Returns a DepositResponse object which will contain the Deposit Receipt or a SWORD Error
        """
        raise NotImplementedError()

    def get_container(self, path, accept_parameters):
        """
        Get a representation of the container in the requested content type
        Args:
        -oid:   The ID of the object in the store
        -content_type   A ContentType object describing the required format
        Returns a representation of the container in the appropriate format
        """
        raise NotImplementedError()

    def deposit_existing(self, path, deposit):
        """
        Deposit the incoming content into an existing object as identified by the supplied identifier
        Args:
        -oid:   The ID of the object we are depositing into
        -deposit:   The DepositRequest object
        Returns a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        raise NotImplementedError()

    def delete_container(self, path, delete):
        """
        Delete the entire object in the store
        Args:
        -oid:   The ID of the object in the store
        -delete:    The DeleteRequest object
        Return a DeleteResponse object with may contain a SWORD Error document or nothing at all
        """
        raise NotImplementedError()

    def get_statement(self, path):
        raise NotImplementedError()

    # NOT PART OF STANDARD, BUT USEFUL    
    # These are used by the webpy interface to provide easy access to certain
    # resources.  Not implementing them is fine.  If they are not implemented
    # then you just have to make sure that your file paths don't rely on the
    # Part http handler
        
    def get_part(self, path):
        """
        Get a file handle to the part identified by the supplied path
        - path:     The URI part which is the path to the file
        """
        raise NotImplementedError()
        
    def get_edit_uri(self, path):
        raise NotImplementedError()
    
class Authenticator(object):
    def __init__(self, config): 
        self.config = config
        
    def basic_authenticate(self, username, password, obo):
        raise NotImplementedError()

class EntryDocument(object):

    def __init__(self, atom_id=None, alternate_uri=None, content_uri=None, edit_uri=None, se_uri=None, em_uris=[], 
                    packaging=[], state_uris=[], updated=None, dc_metadata={}, 
                    generator=("http://www.swordapp.org/sss", __version__), 
                    verbose_description=None, treatment=None, original_deposit_uri=None, derived_resource_uris=[], nsmap=None):
        self.ns = Namespaces()
        self.drmap = {None: self.ns.ATOM_NS, "sword" : self.ns.SWORD_NS, "dcterms" : self.ns.DC_NS}
        if nsmap is not None:
            self.drmap = nsmap
            
        self.dc_metadata = dc_metadata
        self.atom_id = atom_id if atom_id is not None else "urn:uuid:" + str(uuid.uuid4())
        self.updated = updated if updated is not None else datetime.now()
        self.generator = generator
        self.verbose_description = verbose_description
        self.treatment = treatment
        self.alternate_uri = alternate_uri
        self.content_uri = content_uri
        self.edit_uri = edit_uri
        self.em_uris = em_uris
        self.se_uri = se_uri
        self.packaging = packaging
        self.state_uris = state_uris
        self.original_deposit_uri = original_deposit_uri
        self.derived_resource_uris = derived_resource_uris

    def serialise(self):
        # the main entry document room
        entry = etree.Element(self.ns.ATOM + "entry", nsmap=self.drmap)

        # Title from metadata
        title = etree.SubElement(entry, self.ns.ATOM + "title")
        title.text = self.dc_metadata.get('title', ['untitled'])[0]

        # Atom Entry ID
        id = etree.SubElement(entry, self.ns.ATOM + "id")
        id.text = self.atom_id

        # Date last updated
        updated = etree.SubElement(entry, self.ns.ATOM + "updated")
        updated.text = self.updated.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Author field from metadata
        author = etree.SubElement(entry, self.ns.ATOM + "author")
        name = etree.SubElement(author, self.ns.ATOM + "name")
        name.text = self.dc_metadata.get('creator', ["unknown"])[0]

        # Summary field from metadata
        summary = etree.SubElement(entry, self.ns.ATOM + "summary")
        summary.set("type", "text")
        summary.text = self.dc_metadata.get('abstract', [""])[0]

        
        # Generator - identifier for this server software
        gen = etree.SubElement(entry, self.ns.ATOM + "generator")
        gen_uri, version = self.generator
        gen.set("uri", gen_uri)
        gen.set("version", version)

        # now embed all the metadata as foreign markup
        for field in self.dc_metadata.keys():
            for v in self.dc_metadata[field]:
                fdc = etree.SubElement(entry, self.ns.DC + field)
                fdc.text = v

        # verbose description
        if self.verbose_description is not None:
            vd = etree.SubElement(entry, self.ns.SWORD + "verboseDescription")
            vd.text = self.verbose_description

        # treatment
        if self.treatment is not None:
            treatment = etree.SubElement(entry, self.ns.SWORD + "treatment")
            treatment.text = self.treatment

        # link to splash page
        if self.alternate_uri is not None:
            alt = etree.SubElement(entry, self.ns.ATOM + "link")
            alt.set("rel", "alternate")
            alt.set("href", self.alternate_uri)

        # Media Resource Content URI (Cont-URI)
        if self.content_uri is not None:
            content = etree.SubElement(entry, self.ns.ATOM + "content")
            content.set("type", "application/zip")
            content.set("src", self.content_uri)

        # Edit-URI
        if self.edit_uri is not None:
            editlink = etree.SubElement(entry, self.ns.ATOM + "link")
            editlink.set("rel", "edit")
            editlink.set("href", self.edit_uri)
        
        # EM-URI (Media Resource)
        for uri, format in self.em_uris:
            emfeedlink = etree.SubElement(entry, self.ns.ATOM + "link")
            emfeedlink.set("rel", "edit-media")
            if format is not None:
                emfeedlink.set("type", format)
            emfeedlink.set("href", uri)

        # SE-URI (Sword edit - same as media resource)
        if self.se_uri is not None:
            selink = etree.SubElement(entry, self.ns.ATOM + "link")
            selink.set("rel", "http://purl.org/net/sword/terms/add")
            selink.set("href", self.se_uri)

        # supported packaging formats
        for disseminator in self.packaging:
            sp = etree.SubElement(entry, self.ns.SWORD + "packaging")
            sp.text = disseminator

        for uri, format in self.state_uris:
            state1 = etree.SubElement(entry, self.ns.ATOM + "link")
            state1.set("rel", "http://purl.org/net/sword/terms/statement")
            state1.set("type", format)
            state1.set("href", uri)

        # Original Deposit
        if self.original_deposit_uri is not None:
            od = etree.SubElement(entry, self.ns.ATOM + "link")
            od.set("rel", "http://purl.org/net/sword/terms/originalDeposit")
            od.set("href", self.original_deposit_uri)
        
        # Derived Resources
        if self.derived_resource_uris is not None:
            for uri in self.derived_resource_uris:
                dr = etree.SubElement(entry, self.ns.ATOM + "link")
                dr.set("rel", "http://purl.org/net/sword/terms/derivedResource")
                dr.set("href", uri)

        return etree.tostring(entry, pretty_print=True)

class SDCollection(object):
    def __init__(self, href, title, accept=["*/*"], multipart_accept=["*/*"], 
                        description=None, accept_package=[], collection_policy=None, 
                        mediation=False, treatment=None, sub_service=[]):
        self.href = href
        self.title = title
        self.description = description
        self.accept = accept
        self.multipart_accept = multipart_accept
        self.accept_package = accept_package
        self.collection_policy = collection_policy
        self.mediation = mediation
        self.treatment = treatment
        self.sub_service = sub_service
        

class ServiceDocument(object):

    def __init__(self, version="2.0", max_upload_size=0, nsmap=None):
        # set up the namespace declarations that will be used
        self.ns = Namespaces()
        self.sdmap = {None : self.ns.APP_NS, "sword" : self.ns.SWORD_NS, "atom" : self.ns.ATOM_NS, "dcterms" : self.ns.DC_NS}
        if nsmap is not None:
            self.sdmap = nsmap
        
        self.version = version
        self.max_upload_size = max_upload_size
        
        self.workspaces = {}
        
    def add_workspace(self, name, collections):
        self.workspaces[name] = collections
    
    def serialise(self):
        # Start by creating the root of the service document, supplying to it the namespace map in this first instance
        service = etree.Element(self.ns.APP + "service", nsmap=self.sdmap)

        # version element
        version = etree.SubElement(service, self.ns.SWORD + "version")
        version.text = self.version

        # max upload size
        if self.max_upload_size != 0:
            mus = etree.SubElement(service, self.ns.SWORD + "maxUploadSize")
            mus.text = str(self.max_upload_size)

        # workspace element
        for ws in self.workspaces.keys():
            workspace = etree.SubElement(service, self.ns.APP + "workspace")

            # title element
            title = etree.SubElement(workspace, self.ns.ATOM + "title")
            title.text = ws

            # now for each collection create a collection element
            for col in self.workspaces[ws]:
                collection = etree.SubElement(workspace, self.ns.APP + "collection")
                collection.set("href", col.href)

                # collection title
                ctitle = etree.SubElement(collection, self.ns.ATOM + "title")
                ctitle.text = col.title

                for acc in col.accept:
                    accepts = etree.SubElement(collection, self.ns.APP + "accept")
                    accepts.text = acc
                    
                for acc in col.multipart_accept:
                    mraccepts = etree.SubElement(collection, self.ns.APP + "accept")
                    mraccepts.text = acc
                    mraccepts.set("alternate", "multipart-related")

                # SWORD collection policy
                collectionPolicy = etree.SubElement(collection, self.ns.SWORD + "collectionPolicy")
                collectionPolicy.text = col.collection_policy

                # Collection abstract
                abstract = etree.SubElement(collection, self.ns.DC + "abstract")
                abstract.text = col.description

                # support for mediation
                mediation = etree.SubElement(collection, self.ns.SWORD + "mediation")
                mediation.text = "true" if col.mediation else "false"

                # treatment
                treatment = etree.SubElement(collection, self.ns.SWORD + "treatment")
                treatment.text = col.treatment

                # SWORD packaging formats accepted
                for format in col.accept_package:
                    acceptPackaging = etree.SubElement(collection, self.ns.SWORD + "acceptPackaging")
                    acceptPackaging.text = format

                # provide a sub service element if appropriate
                for sub in col.sub_service:
                    subservice = etree.SubElement(collection, self.ns.SWORD + "service")
                    subservice.text = sub

        # pretty print and return
        return etree.tostring(service, pretty_print=True)


# REQUEST/RESPONSE CLASSES
#######################################################################
# These classes are used as the glue between the web.py web interface layer and the underlying sword server, allowing
# them to exchange messages agnostically to the interface

class SwordError(Exception):
    def __init__(self, error_uri=None, msg=None, status=None, verbose_description=None, empty=False):
        self.ns = Namespaces()
        self.emap = {"sword" : self.ns.SWORD_NS, "atom" : self.ns.ATOM_NS}
        
        self.error_uri = error_uri if error_uri is not None else Errors.bad_request
        self.status = status if status is not None else Errors().get_status(self.error_uri)
        if not empty:
            self.error_document = self._generate_error_document(msg, verbose_description)
        else:
            self.error_document = ""
        self.empty = empty
        
    def _generate_error_document(self, msg, verbose_description):
        entry = etree.Element(self.ns.SWORD + "error", nsmap=self.emap)
        entry.set("href", self.error_uri)

        author = etree.SubElement(entry, self.ns.ATOM + "author")
        name = etree.SubElement(author, self.ns.ATOM + "name")
        name.text = "SSS"

        title = etree.SubElement(entry, self.ns.ATOM + "title")
        title.text = "ERROR: " + self.error_uri

        # Date last updated (i.e. NOW)
        updated = etree.SubElement(entry, self.ns.ATOM + "updated")
        updated.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Generator - identifier for this server software
        generator = etree.SubElement(entry, self.ns.ATOM + "generator")
        generator.set("uri", "http://www.swordapp.org/sss")
        generator.set("version", __version__)

        # Summary field from metadata
        summary = etree.SubElement(entry, self.ns.ATOM + "summary")
        summary.set("type", "text")
        text = "Error Description: " + self.error_uri
        if msg is not None:
            text += " ; " + msg
        summary.text = text

        # treatment
        treatment = etree.SubElement(entry, self.ns.SWORD + "treatment")
        treatment.text = "processing failed"
        
        # verbose description
        if verbose_description is not None:
            vb = etree.SubElement(entry, self.ns.SWORD + "verboseDescription")
            vb.text = verbose_description

        return etree.tostring(entry, pretty_print=True)

class AuthException(Exception):
    def __init__(self, authentication_failed=False, target_owner_unknown=False):
        self.authentication_failed = authentication_failed
        self.target_owner_unknown = target_owner_unknown

class Auth(object):
    def __init__(self, by=None, obo=None):
        self.by = by
        self.obo = obo

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
        self.content_type = None
        self.content_length = 0

    def set_from_headers(self, headers):
        for key, value in headers.items():
            if value is not None:
                if key == HttpHeaders.on_behalf_of:
                    self.on_behalf_of = value
                elif key == HttpHeaders.packaging:
                    self.packaging = value
                elif key == HttpHeaders.in_progress:
                    self.in_progress = (value.strip() == "true")
                elif key == HttpHeaders.metadata_relevant:
                    self.metadata_relevant = (value.strip() == "true")
                elif key == HttpHeaders.content_md5:
                    self.content_md5 = value
                elif key == HttpHeaders.slug:
                    self.slug = value
                elif key == HttpHeaders.content_type:
                    self.content_type = value
                elif key == HttpHeaders.content_length:
                    self.content_length = int(value)

    def set_by_header(self, key, value):
        # FIXME: this is a webpy thing....
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
        self.content_type = None

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
    def __init__(self, config):
    
        self.config = config
    
        # FIXME: this is a webpy thing ...
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
        
class WebUI(object):
    def __init__(self, config):
        self.config = config
    
    def get(self, path=None):
        return
