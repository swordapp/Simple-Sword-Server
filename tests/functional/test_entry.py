from . import TestController

from datetime import datetime
from lxml import etree

from sss import EntryDocument

ATOM = "{http://www.w3.org/2005/Atom}"
SWORD = "{http://purl.org/net/sword/terms/}"
DC = "{http://purl.org/dc/terms/}"

class TestConnection(TestController):
    def test_01_blank_init(self):
        e = EntryDocument()
        
        # check the meaningful default values
        assert e.atom_id is not None
        assert e.updated is not None
        
        g, v = e.generator
        assert g == "http://www.swordapp.org/sss"
        assert v is not None
        
        # check a couple of other things for emptyness
        assert e.other_metadata is not None
        assert len(e.other_metadata) == 0
        assert e.dc_metadata is not None
        assert len(e.dc_metadata) == 0
        
    def test_02_args_init(self):
        
        e = EntryDocument(
                atom_id = "1234",
                alternate_uri = "http://alternate/",
                content_uri = "http://content/",
                edit_uri = "http://edit/",
                se_uri = "http://sword-edit/",
                em_uris = [
                    ("http://edit-media/1", "application/atom+xml"),
                    ("http://edit-media/2", "application/zip")
                ],
                packaging = ["http://packaging/"],
                state_uris = [
                    ("http://state/1", "application/atom+xml"),
                    ("http://state/2", "application/rdf+xml")
                ],
                updated = datetime.now(),
                dc_metadata = {
                    "identifier" : "http://identifier/",
                    "rights" : "you can do this!",
                    "replaces" : "something else"
                },
                verbose_description = "Verbose Description",
                treatment = "Treatment",
                original_deposit_uri = "http://original/",
                derived_resource_uris = ["http://derived/1", "http://derived/2"]
            )
    
        assert e.atom_id == "1234"
        assert e.alternate_uri == "http://alternate/"
        assert e.content_uri == "http://content/"
        assert e.edit_uri == "http://edit/"
        assert e.se_uri == "http://sword-edit/"
        assert len(e.em_uris) == 2
        assert "http://edit-media/1" in e.em_uris[0]
        assert "application/zip" in e.em_uris[1]
        assert len(e.packaging) == 1
        assert "http://packaging/" in e.packaging
        assert len(e.state_uris) == 2
        assert "application/atom+xml" in e.state_uris[0]
        assert "http://state/2" in e.state_uris[1]
        assert e.updated is not None
        assert len(e.dc_metadata) == 3
        assert "identifier" in e.dc_metadata.keys()
        assert e.verbose_description == "Verbose Description"
        assert e.treatment == "Treatment"
        assert e.original_deposit_uri == "http://original/"
        assert len(e.derived_resource_uris) == 2

    def test_03_serialise(self):
        e = EntryDocument(
                atom_id = "1234",
                alternate_uri = "http://alternate/",
                content_uri = "http://content/",
                edit_uri = "http://edit/",
                se_uri = "http://sword-edit/",
                em_uris = [
                    ("http://edit-media/1", "application/atom+xml"),
                    ("http://edit-media/2", "application/zip")
                ],
                packaging = ["http://packaging/"],
                state_uris = [
                    ("http://state/1", "application/atom+xml"),
                    ("http://state/2", "application/rdf+xml")
                ],
                updated = datetime.now(),
                dc_metadata = {
                    "identifier" : "http://identifier/",
                    "rights" : "you can do this!",
                    "replaces" : "something else"
                },
                verbose_description = "Verbose Description",
                treatment = "Treatment",
                original_deposit_uri = "http://original/",
                derived_resource_uris = ["http://derived/1", "http://derived/2"]
            )
            
        s = e.serialise()
        
        # does it parse as xml
        xml = etree.fromstring(s)
        
        # now check the xml document and see if it ties in with the above
        # attributes
        has_id = False
        has_alt = False
        has_cont = False
        has_edit = False
        has_se = False
        has_em_atom = False
        has_em_zip = False
        has_packaging = False
        has_state_atom = False
        has_state_rdf = False
        has_updated = False
        dc_count = 0
        has_vd = False
        has_treatment = False
        has_od = False
        dr_count = 0
        for element in xml.getchildren():
            if element.tag == ATOM + "id":
                assert element.text.strip() == "1234"
                has_id = True
            elif element.tag == ATOM + "content":
                src = element.attrib.get("src")
                assert src == "http://content/"
                has_cont = True
            elif element.tag == SWORD + "packaging":
                assert element.text.strip() == "http://packaging/"
                has_packaging = True
            elif element.tag == ATOM + "updated":
                has_updated = True
            elif element.tag == DC + "identifier":
                assert element.text.strip() == "http://identifier/"
                dc_count += 1
            elif element.tag == DC + "rights":
                assert element.text.strip() == "you can do this!"
                dc_count += 1
            elif element.tag == DC + "replaces":
                assert element.text.strip() == "something else"
                dc_count += 1
            elif element.tag == SWORD + "verboseDescription":
                assert element.text.strip() == "Verbose Description"
                has_vd = True
            elif element.tag == SWORD + "treatment":
                assert element.text.strip() == "Treatment"
                has_treatment = True
            elif element.tag == ATOM + "link":
                rel = element.attrib.get("rel")
                if rel == "alternate":
                    assert element.attrib.get("href") == "http://alternate/"
                    has_alt = True
                elif rel == "edit":
                    assert element.attrib.get("href") == "http://edit/"
                    has_edit = True
                elif rel == "http://purl.org/net/sword/terms/add":
                    assert element.attrib.get("href") == "http://sword-edit/"
                    has_se= True
                elif rel == "edit-media":
                    t = element.attrib.get("type")
                    if t == "application/atom+xml":
                        assert element.attrib.get("href") == "http://edit-media/1"
                        has_em_atom = True
                    elif t == "application/zip":
                        assert element.attrib.get("href") == "http://edit-media/2"
                        has_em_zip = True
                    else:
                        assert False
                elif rel == "http://purl.org/net/sword/terms/statement":
                    t = element.attrib.get("type")
                    if t == "application/atom+xml":
                        assert element.attrib.get("href") == "http://state/1"
                        has_state_atom = True
                    elif t == "application/rdf+xml":
                        assert element.attrib.get("href") == "http://state/2"
                        has_state_rdf = True
                    else:
                        assert False
                elif rel == "http://purl.org/net/sword/terms/originalDeposit":
                    assert element.attrib.get("href") == "http://original/"
                    has_od = True
                elif rel == "http://purl.org/net/sword/terms/derivedResource":
                    assert element.attrib.get("href") in ["http://derived/1", "http://derived/2"]
                    dr_count += 1
        
        # now check all our switches were appropriately thrown
        assert has_id
        assert has_alt
        assert has_cont
        assert has_edit
        assert has_se
        assert has_em_atom
        assert has_em_zip
        assert has_packaging
        assert has_state_atom
        assert has_state_rdf
        assert has_updated
        assert dc_count == 3
        assert has_vd
        assert has_treatment
        assert has_od
        assert dr_count == 2
        
    def test_04_round_trip_load(self):
        e1 = EntryDocument(
                atom_id = "1234",
                alternate_uri = "http://alternate/",
                content_uri = "http://content/",
                edit_uri = "http://edit/",
                se_uri = "http://sword-edit/",
                em_uris = [
                    ("http://edit-media/1", "application/atom+xml"),
                    ("http://edit-media/2", "application/zip")
                ],
                packaging = ["http://packaging/"],
                state_uris = [
                    ("http://state/1", "application/atom+xml"),
                    ("http://state/2", "application/rdf+xml")
                ],
                updated = datetime.now(),
                dc_metadata = {
                    "identifier" : "http://identifier/",
                    "rights" : "you can do this!",
                    "replaces" : "something else"
                },
                verbose_description = "Verbose Description",
                treatment = "Treatment",
                original_deposit_uri = "http://original/",
                derived_resource_uris = ["http://derived/1", "http://derived/2"]
            )
            
        s = e1.serialise()
        
        # now create a new entry from the output
        e = EntryDocument(xml_source=s)
        
        assert e.atom_id == "1234"
        assert e.alternate_uri == "http://alternate/"
        assert e.content_uri == "http://content/"
        assert e.edit_uri == "http://edit/"
        assert e.se_uri == "http://sword-edit/"
        assert len(e.em_uris) == 2
        assert "http://edit-media/1" in e.em_uris[0]
        assert "application/zip" in e.em_uris[1]
        assert len(e.packaging) == 1
        assert "http://packaging/" in e.packaging
        assert len(e.state_uris) == 2
        assert "application/atom+xml" in e.state_uris[0]
        assert "http://state/2" in e.state_uris[1]
        assert e.updated is not None
        assert len(e.dc_metadata) == 3
        assert "identifier" in e.dc_metadata.keys()
        assert e.verbose_description == "Verbose Description"
        assert e.treatment == "Treatment"
        assert e.original_deposit_uri == "http://original/"
        assert len(e.derived_resource_uris) == 2

        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
