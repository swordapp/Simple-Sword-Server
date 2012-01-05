import os
from repository import DAO

# create the global configuration
from config import CherryPyConfiguration
global_configuration = CherryPyConfiguration()

from sss_logging import logging
ssslog = logging.getLogger(__name__)

# Basic Web Interface
#######################################################################

class WebPage(object):
    def _wrap_html(self, title, frag, head_frag=None):
        return "<html><head><title>" + title + "</title>" + head_frag + "</head><body>" + frag + "</body></html>"

class HomePage(WebPage):
    """
    Welcome / home page
    """
    def __init__(self, uri_manager):
        self.dao = DAO()
        self.um = uri_manager
        
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
    def __init__(self, uri_manager):
        self.dao = DAO()
        self.um = uri_manager
        
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
    def __init__(self, uri_manager):
        self.dao = DAO()
        self.um = uri_manager
    
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
