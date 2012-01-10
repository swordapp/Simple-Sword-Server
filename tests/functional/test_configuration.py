import os

from . import TestController

from sss import Configuration, SSS_CONFIG_FILE
from sss.negotiator import AcceptParameters

class TestEntry(TestController):
    def test_01_init(self):
        # before beginning, remove any existing configuration file
        if os.path.isfile(SSS_CONFIG_FILE):
            os.remove(SSS_CONFIG_FILE)
    
        c = Configuration()
    
        # check that the config file specified exists/has been created
        assert os.path.isfile(c.SSS_CONFIG_FILE)
        
        # check that the configuration has been loaded successfully
        assert c.cfg is not None
        
        # check that __getattr__ is behaving correctly
        assert c.ajklsdhfoiqajriojwelkasfljw is None
        
        # check that we can set and retrieve ingesters and disseminators
        c.package_disseminators = { "(& (application/zip))" : "sss.ingesters_disseminators.DefaultDisseminator" }
        c.package_ingesters = { "http://whatever/" :  "sss.ingesters_disseminators.BinaryIngester"}
        
        # should be able to get back an class handle for DefaultDisseminator
        klazz = c.get_package_disseminator("(& (application/zip))")
        assert klazz.__name__ == "DefaultDisseminator"
        
        # and one for DefaultIngester
        clazz = c.get_package_ingester("http://whatever/")
        assert clazz.__name__ == "BinaryIngester"
        
        # should also get None when we ask for something else
        assert c.get_package_disseminator("other") is None
        assert c.get_package_ingester("other") is None
        
        # check that we can get accept parameters for the media formats
        c.media_resource_formats = [
            {"content_type" : "application/zip", "packaging" : "http://purl.org/net/sword/package/SimpleZip"},
            {"content_type" : "application/zip"},
            {"content_type" : "application/atom+xml;type=feed"},
            {"content_type" : "text/html"}
        ]
        c.media_resource_default = {
            "content_type" : "application/zip"
        }
        
        default, acceptable = c.get_media_resource_formats()
        
        assert isinstance(default, AcceptParameters)
        assert len(acceptable) == 4
        
        assert default.content_type.mimetype() == "application/zip"
        
        for acc in acceptable:
            assert isinstance(acc, AcceptParameters)
            assert acc.content_type.mimetype() == "application/zip" or acc.content_type.mimetype() == "application/atom+xml;type=feed" or acc.content_type.mimetype() == "text/html"
            if acc.packaging is not None:
                assert acc.packaging == "http://purl.org/net/sword/package/SimpleZip"
