from sss_logging import logging
ssslog = logging.getLogger(__name__)

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

