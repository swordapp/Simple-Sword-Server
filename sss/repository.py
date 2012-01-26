import os, hashlib, uuid, urllib
from core import Statement, DepositResponse, MediaResourceResponse, DeleteResponse, Auth, AuthException, SwordError, ServiceDocument, SDCollection, EntryDocument, Authenticator, SwordServer, WebUI
from spec import Namespaces, Errors
from lxml import etree
from datetime import datetime
from zipfile import ZipFile
from negotiator import AcceptParameters, ContentType
from info import __version__

from sss_logging import logging
ssslog = logging.getLogger(__name__)

class WebInterface(WebUI):
    def get(self, path=None):
        if path is not None:
            if path.find("/") >= 0:
                ip = ItemPage(self.config)
                return ip.get_item_page(path)
            else:
                cp = CollectionPage(self.config)
                return cp.get_collection_page(path)
        else:
            hp = HomePage(self.config)
            return hp.get_home_page()

class SSSAuthenticator(Authenticator):
    def __init__(self, config):
        Authenticator.__init__(self, config)
    
    def basic_authenticate(self, username, password, obo):
        # we may have turned authentication off for development purposes
        if not self.config.authenticate:
            ssslog.info("Authentication is turned OFF")
            return Auth(self.config.user)
        else:
            ssslog.info("Authentication required")
        
        # if the username and password don't match, bounce the user with a 401
        # meanwhile if the obo header has been passed but doesn't match the config value also bounce
        # with a 401 (I know this is an odd looking if/else but it's for clarity of what's going on
        if username != self.config.user or password != self.config.password:
            ssslog.info("Authentication Failed; returning 401")
            raise AuthException(authentication_failed=True)
        elif obo is not None and obo != self.config.obo:
            ssslog.info("Authentication Failed with Target Owner Unknown")
            # we throw a sword error for TargetOwnerUnknown
            raise AuthException(target_owner_unknown=True)
            
        if obo is not None:
            return Auth(self.config.user, obo)
        return Auth(self.config.user)

class URIManager(object):
    """
    Class for providing a single point of access to all identifiers used by SSS
    """
    def __init__(self, config):
        self.configuration = config

    def interpret_statement_path(self, path):
        accept_parameters = None
        if path.endswith("rdf"):
            accept_parameters = AcceptParameters(ContentType("application/rdf+xml"))
            path = path[:-4]
        elif path.endswith("atom"):
            accept_parameters = AcceptParameters(ContentType("application/atom+xml;type=feed"))
            path = path[:-5]

        return accept_parameters, path

    def is_atom_path(self, path):
        atom = False
        if path.endswith(".atom"):
            path = path[:-5]
            atom = True
        return atom, path

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

class SSS(SwordServer):
    """
    The main SWORD Server class.  This class deals with all the CRUD requests as provided by the web.py HTTP
    handlers
    """
    def __init__(self, config, auth):
        SwordServer.__init__(self, config, auth)

        # create a DAO for us to use
        self.dao = DAO(self.configuration)

        # create a Namespace object for us to use
        self.ns = Namespaces()

        # create a URIManager for us to use
        self.um = URIManager(self.configuration)
        
        # URIs to use for the two supported states in SSS
        self.in_progress_uri = "http://purl.org/net/sword/state/in-progress"
        self.archived_uri = "http://purl.org/net/sword/state/archived"

        # the descriptions to associated with the two supported states in SSS
        self.states = {
            self.in_progress_uri : "The work is currently in progress, and has not passed to a reviewer",
            self.archived_uri : "The work has passed through review and is now in the archive"
        }

        # build the namespace maps that we will use during serialisation
        # self.sdmap = {None : self.ns.APP_NS, "sword" : self.ns.SWORD_NS, "atom" : self.ns.ATOM_NS, "dcterms" : self.ns.DC_NS}
        self.cmap = {None: self.ns.ATOM_NS}
        # self.drmap = {None: self.ns.ATOM_NS, "sword" : self.ns.SWORD_NS, "dcterms" : self.ns.DC_NS}
        self.smap = {"rdf" : self.ns.RDF_NS, "ore" : self.ns.ORE_NS, "sword" : self.ns.SWORD_NS}
        self.emap = {"sword" : self.ns.SWORD_NS, "atom" : self.ns.ATOM_NS}

    def container_exists(self, oid):
        # find out some details about the statement we are to deliver
        accept_parameters, path = self.um.interpret_statement_path(oid)
        return self.exists(path)

    def media_resource_exists(self, oid):
        # check to see if we're after the .atom version of the content
        # also strips the .atom if necessary
        atom, path = self.um.is_atom_path(oid)
        return self.exists(path)

    def exists(self, oid):
        """
        Does the specified object id exist?
        """
        collection, id = oid.split("/", 1)
        return self.dao.collection_exists(collection) and self.dao.container_exists(collection, id)

    def service_document(self, path=None):
        """
        Construct the Service Document.  This takes the set of collections that are in the store, and places them in
        an Atom Service document as the individual entries
        """
        use_sub = self.configuration.use_sub if path is None else False
        
        service = ServiceDocument(version=self.configuration.sword_version,
                                    max_upload_size=self.configuration.max_upload_size)
        
        # now for each collection create an sdcollection
        collections = []
        for col_name in self.dao.get_collection_names():
            href = self.um.col_uri(col_name)
            title = "Collection " + col_name
            policy = "Collection Policy"
            abstract = "Collection Description"
            mediation = self.configuration.mediation
            treatment = "Treatment description"
            
            # content types accepted
            accept = []
            multipart_accept = []
            if not self.configuration.accept_nothing:
                if self.configuration.app_accept is not None:
                    for acc in self.configuration.app_accept:
                        accept.append(acc)
                
                if self.configuration.multipart_accept is not None:
                    for acc in self.configuration.multipart_accept:
                        multipart_accept.append(acc)
                        
            # SWORD packaging formats accepted
            accept_package = []
            for format in self.configuration.sword_accept_package:
                accept_package.append(format)

            # provide a sub service element if appropriate
            subservice = []
            if use_sub:
                subservice.append(self.um.sd_uri(True))
            
            col = SDCollection(href=href, title=title, accept=accept, multipart_accept=multipart_accept,
                                description=abstract, accept_package=accept_package, 
                                collection_policy=policy, mediation=mediation, treatment=treatment,
                                sub_service=subservice)
                                
            collections.append(col)
        
        service.add_workspace("Main Site", collections)

        # serialise and return
        return service.serialise()

    def list_collection(self, id):
        """
        List the contents of a collection identified by the supplied id
        """
        # FIXME: would be good to have this in the generic implementation (section
        # 6.2), but that's a future task; for the time being this remains a
        # repository specific piece of code, and a generic implementation will
        # be done later
        
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
        # check for standard possible errors, raises an exception if appropriate
        self.check_deposit_errors(deposit)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.dao.collection_exists(collection):
            raise SwordError(status=404, empty=True)

        # create us a new container, passing in the Slug value (which may be None) as the proposed id
        id = self.dao.create_container(collection, deposit.slug)

        # store the incoming atom document if necessary
        if deposit.atom is not None:
            entry_ingester = self.configuration.get_entry_ingester()(self.dao)
            entry_ingester.ingest(collection, id, deposit.atom)

        # store the content file if one exists, and do some processing on it
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
        
            if deposit.filename is None:
                deposit.filename = "unnamed.file"
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want
            
            # FIXME: because the deposit interpreter doesn't deal with multipart properly
            # we don't get the correct packaging format here if the package is anything
            # other than Binary
            ssslog.info("attempting to load ingest packager for format " + str(deposit.packaging))
            packager = self.configuration.get_package_ingester(deposit.packaging)(self.dao)
            derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)
            
            # a list of identifiers which will resolve to the derived resources
            derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

        # the aggregation uri
        agg_uri = self.um.agg_uri(collection, id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(collection, id)
        
        # State information
        state_uri = self.in_progress_uri if deposit.in_progress else self.archived_uri
        state_description = self.states[state_uri]
        
        # create the initial statement
        s = Statement()
        s.aggregation_uri = agg_uri
        s.rem_uri = edit_uri
        by = deposit.auth.username if deposit.auth is not None else None
        obo = deposit.auth.on_behalf_of if deposit.auth is not None else None
        if deposit_uri is not None:
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        s.aggregates = derived_resource_uris
        s.add_state(state_uri, state_description)
        
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
        dr.receipt = receipt.serialise()
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

    def get_media_resource(self, oid, accept_parameters):
        """
        Get a representation of the media resource for the given id as represented by the specified content type
        -id:    The ID of the object in the store
        -content_type   A ContentType object describing the type of the object to be retrieved
        """
        # by the time this is called, we should already know that we can return this type, so there is no need for
        # any checking, we just get on with it

        # requesting from the atom URI will get you the atom format, irrespective
        # of the content negotiation
        atom, path = self.um.is_atom_path(oid)
        if atom:
            ssslog.info("Received request for atom feed form of media resource")
            accept_parameters = AcceptParameters(ContentType("application/atom+xml;type=feed"))
        else:
            ssslog.info("Received request for package form of media resource")

        # did we successfully negotiate a content type?
        if accept_parameters is None:
            raise SwordError(error_uri=Errors.content, status=406, msg="Requsted Accept/Accept-Packaging is not supported by this server")

        ssslog.info("Request media type with media format: " + accept_parameters.media_format())

        # ok, so break the id down into collection and object
        collection, id = self.um.interpret_oid(path)

        # make a MediaResourceResponse object for us to use
        mr = MediaResourceResponse()

        # if the type/subtype is text/html, then we need to do a redirect.  This is equivalent to redirecting the
        # client to the splash page of the item on the server
        if accept_parameters.content_type.mimetype() == "text/html":
            ssslog.info("Requested format is text/html ... redirecting client to web ui")
            mr.redirect = True
            mr.url = self.um.html_url(collection, id)
            return mr
        
        # call the appropriate packager, and get back the filepath for the response
        packager = self.configuration.get_package_disseminator(accept_parameters.media_format())(self.dao, self.um)
        mr.filepath = packager.package(collection, id)
        mr.packaging = packager.get_uri()
        mr.content_type = accept_parameters.content_type.mimetype()

        return mr
    
    def replace(self, oid, deposit):
        """
        Replace all the content represented by the supplied id with the supplied deposit
        Args:
        - oid:  the object ID in the store
        - deposit:  a DepositRequest object
        Return a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        # check for standard possible errors, raises an exception if appropriate
        self.check_deposit_errors(deposit)

        collection, id = self.um.interpret_oid(oid)

        # does the object directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return SwordError(status=404, empty=True)
                
        # first figure out what to do about the metadata
        keep_atom = False
        if deposit.atom is not None:
            ssslog.info("Replace request has ATOM part - updating")
            entry_ingester = self.configuration.get_entry_ingester()(self.dao)
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
            if deposit.filename is None:
                deposit.filename = "unnamed.file"
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)
            ssslog.debug("New incoming file stored with filename " + fn)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want.  Notice that we pass in the metadata_relevant flag, so the
            # packager won't overwrite the existing metadata if it isn't supposed to
            packager = self.configuration.get_package_ingester(deposit.packaging)(self.dao)
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
        
        # State information
        state_uri = self.in_progress_uri if deposit.in_progress else self.archived_uri
        state_description = self.states[state_uri]

        # create the new statement
        s = Statement()
        s.aggregation_uri = agg_uri
        s.rem_uri = edit_uri
        if deposit_uri is not None:
            by = deposit.auth.username if deposit.auth is not None else None
            obo = deposit.auth.on_behalf_of if deposit.auth is not None else None
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        s.add_state(state_uri, state_description)
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
        dr.receipt = receipt.serialise()
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
        
        # check for standard possible errors, this throws an error if appropriate
        self.check_delete_errors(delete)

        collection, id = self.um.interpret_oid(oid)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            raise SwordError(status=404, empty=True)

        # remove all the old files before adding the new.
        # notice that we keep the metadata, as this is considered bound to the
        # container and not the media resource.
        self.dao.remove_content(collection, id, True)

        # the aggregation uri
        agg_uri = self.um.agg_uri(collection, id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(collection, id)

        # State information
        state_uri = self.in_progress_uri if delete.in_progress else self.archived_uri
        state_description = self.states[state_uri]
    
        # create the statement
        s = Statement()
        s.aggregation_uri = agg_uri
        s.rem_uri = edit_uri
        s.add_state(state_uri, state_description)

        # store the statement by itself
        self.dao.store_statement(collection, id, s)

        # create the deposit receipt (which involves getting hold of the item's metadata first if it exists
        metadata = self.dao.get_metadata(collection, id)
        receipt = self.deposit_receipt(collection, id, delete, s, metadata)

        # store the deposit receipt also
        self.dao.store_deposit_receipt(collection, id, receipt)

        # finally, assemble the delete response and return
        dr = DeleteResponse()
        dr.receipt = receipt.serialise()
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
        
        # check for standard possible errors, raises an exception if appropriate
        self.check_deposit_errors(deposit)

        collection, id = self.um.interpret_oid(oid)
        
        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            raise SwordError(status=404, empty=True)

        # State information
        state_uri = self.in_progress_uri if deposit.in_progress else self.archived_uri
        state_description = self.states[state_uri]

        # load the statement
        s = self.dao.load_statement(collection, id)
        s.set_state(state_uri, state_description)
        
        # store the content file if one exists, and do some processing on it
        location_uri = None
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
            ssslog.debug("Add request contains content part")
            
            if deposit.filename is None:
                deposit.filename = "unnamed.file"
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)
            ssslog.debug("New incoming file stored with filename " + fn)
                
            packager = self.configuration.get_package_ingester(deposit.packaging)(self.dao)
            derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)
            ssslog.debug("Resources derived from deposit: " + str(derived_resources))

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)
            
            by = deposit.auth.username if deposit.auth is not None else None
            obo = deposit.auth.on_behalf_of if deposit.auth is not None else None
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
        dr.receipt = receipt.serialise()
        dr.location = location_uri
        dr.created = True
        return dr

    def get_edit_uri(self, path):
        col, oid = self.um.interpret_oid(path)
        return self.um.edit_uri(col, oid)
    
    def get_container(self, oid, accept_parameters):
        """
        Get a representation of the container in the requested content type
        Args:
        -oid:   The ID of the object in the store
        -content_type   A ContentType object describing the required format
        Returns a representation of the container in the appropriate format
        """
        # by the time this is called, we should already know that we can return this type, so there is no need for
        # any checking, we just get on with it

        ssslog.info("Container requested in mime format: " + accept_parameters.content_type.mimetype())

        # ok, so break the id down into collection and object
        collection, id = self.um.interpret_oid(oid)

        # pick either the deposit receipt or the pure statement to return to the client
        if accept_parameters.content_type.mimetype() == "application/atom+xml;type=entry":
            return self.dao.get_deposit_receipt_content(collection, id)
        elif accept_parameters.content_type.mimetype() == "application/rdf+xml":
            return self.dao.get_statement_content(collection, id)
        elif accept_parameters.content_type.mimetype() == "application/atom+xml;type=feed":
            return self.dao.get_statement_feed(collection, id)
        else:
            ssslog.info("Requested mimetype not recognised/supported: " + accept_parameters.content_type.mimetype())
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
        
        # check for standard possible errors, raises an exception if appropriate
        self.check_deposit_errors(deposit)

        collection, id = self.um.interpret_oid(oid)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            raise SwordError(status=404, empty=True)

        # State information
        state_uri = self.in_progress_uri if deposit.in_progress else self.archived_uri
        state_description = self.states[state_uri]

        # load the statement
        s = self.dao.load_statement(collection, id)
        
        # do the in-progress first, as some deposits will be empty, and will
        # just be telling us that the client has finished working on this item
        s.set_state(state_uri, state_description)
        
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
            entry_ingester = self.configuration.get_entry_ingester()(self.dao)
            entry_ingester.ingest(collection, id, deposit.atom, True)

        # store the content file
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content is not None:
            ssslog.info("Append request has file content - adding to media resource")
            
            if deposit.filename is None:
                deposit.filename = "unnamed.file"
            fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)
            ssslog.debug("New incoming file stored with filename " + fn)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want.  Notice that we pass in the metadata_relevant flag, so the packager
            # won't overwrite the metadata if it isn't supposed to
            pclass = self.configuration.get_package_ingester(deposit.packaging)
            if pclass is not None:
                packager = pclass(self.dao)
                derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)
                ssslog.debug("Resources derived from deposit: " + str(derived_resources))
                
                # a list of identifiers which will resolve to the derived resources
                derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.part_uri(collection, id, fn)

            # add the new deposit
            by = deposit.auth.username if deposit.auth is not None else None
            obo = deposit.auth.on_behalf_of if deposit.auth is not None else None
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
        dr.receipt = receipt.serialise()
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
        self.check_delete_errors(delete)
            
        collection, id = self.um.interpret_oid(oid)

        # does the collection directory exist?  If not, we can't do a deposit
        if not self.exists(oid):
            return SwordError(status=404, empty=True)

        # request the deletion of the container
        self.dao.remove_container(collection, id)
        return DeleteResponse()

    def get_derived_resource_uris(self, collection, id, derived_resource_names):
        uris = []
        for name in derived_resource_names:
            uris.append(self.um.part_uri(collection, id, name))
        return uris

    def augmented_receipt(self, receipt, original_deposit_uri, derived_resource_uris=[]):
        receipt.original_deposit_uri = original_deposit_uri
        receipt.derived_resource_uris = derived_resource_uris     
        return receipt

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

        # the EM-URI 
        em_uri = self.um.em_uri(collection, id)
        em_uris = [(em_uri, None), (em_uri + ".atom", "application/atom+xml;type=feed")]

        # the Edit-URI and SE-IRI
        edit_uri = self.um.edit_uri(collection, id)
        se_uri = edit_uri

        # the splash page URI
        splash_uri = self.um.html_url(collection, id)

        # the two statement uris
        atom_statement_uri = self.um.state_uri(collection, id, "atom")
        ore_statement_uri = self.um.state_uri(collection, id, "ore")
        state_uris = [(atom_statement_uri, "application/atom+xml;type=feed"), (ore_statement_uri, "application/rdf+xml")]

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

        packaging = []
        for disseminator in self.configuration.sword_disseminate_package:
            packaging.append(disseminator)

        verbose_description = "SSS has done this, that and the other to process the deposit"
        treatment="Treatment description"

        # Now assemble the deposit receipt
        dr = EntryDocument(atom_id=drid, alternate_uri=splash_uri, content_uri=cont_uri,
                            edit_uri=edit_uri, se_uri=se_uri, em_uris=em_uris,
                            packaging=packaging, state_uris=state_uris, dc_metadata=metadata,
                            verbose_description=verbose_description, treatment=treatment)

        return dr

    def get_statement(self, oid):
        accept_parameters, path = self.um.interpret_statement_path(oid)
        collection, id = self.um.interpret_oid(path)
        if accept_parameters.content_type.mimetype() == "application/rdf+xml":
            return self.dao.get_statement_content(collection, id)
        elif accept_parameters.content_type.mimetype() == "application/atom+xml;type=feed":
            return self.dao.get_statement_feed(collection, id)
        else:
            return None

    def check_delete_errors(self, delete):
        # have we been asked to do a mediated delete, when this is not allowed?
        if delete.auth is not None:
            if delete.auth.on_behalf_of is not None and not self.configuration.mediation:
                raise SwordError(Errors.mediation_not_allowed)

    def check_deposit_errors(self, deposit):
        # have we been asked for an invalid package format
        if deposit.packaging == self.configuration.error_content_package:
            raise SwordError(error_uri=Errors.content, status=415, msg="Unsupported Packaging format specified")

        # have we been given an incompatible MD5?
        if deposit.content_md5 is not None:
            m = hashlib.md5()
            m.update(deposit.content)
            digest = m.hexdigest()
            if digest != deposit.content_md5:
                raise SwordError(error_uri=Errors.checksum_mismatch, msg="Content-MD5 header does not match file checksum")

        # have we been asked to do a mediated deposit, when this is not allowed?
        if deposit.auth is not None:
            if deposit.auth.on_behalf_of is not None and not self.configuration.mediation:
                raise SwordError(error_uri=Errors.mediation_not_allowed)

        return None

class DAO(object):
    """
    Data Access Object for interacting with the store
    """
    def __init__(self, config):
        """
        Initialise the DAO.  This creates the store directory in the Configuration() object if it does not already
        exist and will construct the relevant number of fake collections.  In general if you make changes to the
        number of fake collections you want to have, it's best just to burn the store and start from scratch, although
        this method will check to see that it has enough fake collections and make up the defecit, but it WILL NOT
        remove excess collections
        """
        self.configuration = config

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
        self.save(sfile, statement.serialise_rdf())
        # store the Atom Feed version
        sfile = os.path.join(self.configuration.store_dir, collection, id, "sss_statement.atom.xml")
        self.save(sfile, statement.serialise_atom())

    def store_deposit_receipt(self, collection, id, receipt):
        """ Store the supplied receipt document content in the object idenfied by the id in the specified collection """
        drfile = os.path.join(self.configuration.store_dir, collection, id, "sss_deposit-receipt.xml")
        if not isinstance(receipt, str):
            receipt = receipt.serialise()
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
        s = Statement(rdf_file=sfile)
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

# Basic Web Interface
#######################################################################

class WebPage(object):
    def _wrap_html(self, title, frag, head_frag=None):
        return "<html><head><title>" + title + "</title>" + head_frag + "</head><body>" + frag + "</body></html>"

class HomePage(WebPage):
    """
    Welcome / home page
    """
    def __init__(self, config):
        self.config = config
        self.dao = DAO(self.config)
        self.um = URIManager(config)
        
    def get_home_page(self):
        frag = "<h1>Simple SWORDv2 Server</h1>"
        frag += "<p><strong>Service Document (SD-IRI)</strong>: <a href=\"" + self.config.base_url + "sd-uri\">" + self.config.base_url + "sd-uri</a></p>"
        frag += "<p>If prompted, use the username <strong>" + self.config.user + "</strong> and the password <strong>" + self.config.password + "</strong></p>"
        frag += "<p>The On-Behalf-Of user to use is <strong>" + self.config.obo + "</strong></p>"
        
        # list the collections
        frag += "<h2>Collections</h2><ul>"
        for col in self.dao.get_collection_names():
            frag += "<li><a href=\"" + self.um.html_url(col) + "\">" + col + "</a></li>"
        frag += "</ul>"
        
        head_frag = "<link rel=\"http://purl.org/net/sword/discovery/service-document\" href=\"" + self.config.base_url + "sd-uri\"/>"
        
        return self._wrap_html("Simple SWORDv2 Server", frag, head_frag)

class CollectionPage(WebPage):
    def __init__(self, config):
        self.config = config
        self.dao = DAO(config)
        self.um = URIManager(config)
        
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
    def __init__(self, config):
        self.config = config
        self.dao = DAO(config)
        self.um = URIManager(config)
    
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
