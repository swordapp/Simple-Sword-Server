import os
from lxml import etree
from datetime import datetime

from . import TestController

from sss import Statement

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
ORE = "{http://www.openarchives.org/ore/terms/}"
SWORD = "{http://purl.org/net/sword/terms/}"
OX = "{http://vocab.ox.ac.uk/dataset/schema#}"
DC = "{http://purl.org/dc/terms/}"

RDF_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF
   xmlns:dcterms="http://purl.org/dc/terms/"
   xmlns:ore="http://www.openarchives.org/ore/terms/"
   xmlns:oxds="http://vocab.ox.ac.uk/dataset/schema#"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
>
  <rdf:Description rdf:about="http://192.168.23.133/asdfasd/datasets/mydataset6">
    <oxds:currentVersion>6</oxds:currentVersion>
    <oxds:embargoedUntil>2081-12-30T13:20:10.864975</oxds:embargoedUntil>
    <oxds:isEmbargoed>True</oxds:isEmbargoed>
    <dcterms:identifier>mydataset6</dcterms:identifier>
    <dcterms:modified>2012-01-17 18:33:10.228565</dcterms:modified>
    <dcterms:rights rdf:resource="http://ora.ouls.ox.ac.uk/objects/uuid%3A1d00eebb-8fed-46ad-8e38-45dbdb4b224c"/>
    <rdf:type rdf:resource="http://vocab.ox.ac.uk/dataset/schema#DataSet"/>
    <dcterms:publisher>Bodleian Libraries, University of Oxford</dcterms:publisher>
    <dcterms:created>2012-01-17 13:20:10.865789</dcterms:created>
    <dcterms:mediator></dcterms:mediator>
    <ore:aggregates rdf:resource="http://192.168.23.133/asdfasd/datasets/mydataset6/example.zip"/>
  </rdf:Description>
</rdf:RDF>
"""

class TestEntry(TestController):
    def test_01_init_statement(self):
        n = datetime.now()
        ods = [
            ("http://od1/", n, "http://package/", "sword", "obo"),
            ("http://od2/", n, "http://package/", "bob", None)
        ]
        s = Statement(aggregation_uri="http://aggregation/", rem_uri="http://rem/",
                        original_deposits=ods,
                        aggregates=["http://od1/", "http://od2/", "http://agg1/", "http://agg2/"],
                        states=[("http://state/", "everything is groovy")])
        
        # now check that the item is correctly initialised
        assert s.aggregation_uri == "http://aggregation/"
        assert s.rem_uri == "http://rem/"
        assert len(s.original_deposits) == 2
        assert "http://od1/" in s.original_deposits[0]
        assert "http://od2/" in s.original_deposits[1]
        assert "http://od1/" in s.aggregates
        assert "http://od2/" in s.aggregates
        assert "http://agg1/" in s.aggregates
        assert "http://agg2/" in s.aggregates
        assert len(s.aggregates) == 4
        assert len(s.states) == 1
        
        state_uri, state_description = s.states[0]
        assert state_uri == "http://state/"
        assert state_description == "everything is groovy"
        
    def test_02_modify_statement(self):
        n = datetime.now()
        ods = [
            ("http://od1/", n, "http://package/", "sword", "obo"),
            ("http://od2/", n, "http://package/", "bob", None)
        ]
        s = Statement(aggregation_uri="http://aggregation/", rem_uri="http://rem/",
                        original_deposits=ods,
                        aggregates=["http://od1/", "http://od2/", "http://agg1/", "http://agg2/"],
                        states=[("http://state/", "everything is groovy")])
        
        s.set_state("http://new/state/", "still good, though")
        
        assert len(s.states) == 1
        state_uri, state_description = s.states[0]
        assert state_uri == "http://new/state/"
        assert state_description == "still good, though"
        
        s.add_state("http://another/state", "also, this")
        assert len(s.states) == 2
        
    def test_03_rdf_serialise(self):
        n = datetime.now()
        ods = [
            ("http://od1/", n, "http://package/", "sword", "obo"),
            ("http://od2/", n, "http://package/", "bob", None)
        ]
        od_uris = ["http://od1/", "http://od2/"]
        s = Statement(aggregation_uri="http://aggregation/", rem_uri="http://rem/",
                        original_deposits=ods,
                        aggregates=["http://od1/", "http://od2/", "http://agg1/", "http://agg2/"],
                        states=[("http://state/", "everything is groovy")])
                        
        rdf_string = s.serialise_rdf()
        
        # first try the round trip
        rdf = etree.fromstring(rdf_string)
        
        # here are some counters/switches which will help us test that everything
        # is good within the statement
        descriptions = 0
        states = 0
        state_descriptions = 0
        original_deposits = 0
        aggregated_resources = 0
        packaging = 0
        dep_on = 0
        dep_by = 0
        dep_obo = 0
        
        has_rem_description = False
        has_agg_description = False
        
        # now go through the rdf and check that everything is as expected
        for desc in rdf.findall(RDF + "Description"):
            descriptions += 1
            about = desc.get(RDF + "about")
            for element in desc.getchildren():
                if element.tag == ORE + "describes":
                    resource = element.get(RDF + "resource")
                    assert about == s.rem_uri
                    assert resource == s.aggregation_uri
                    has_rem_description = True
                if element.tag == ORE + "isDescribedBy":
                    resource = element.get(RDF + "resource")
                    assert about == s.aggregation_uri
                    assert resource == s.rem_uri
                    has_agg_description = True
                if element.tag == ORE + "aggregates":
                    resource = element.get(RDF + "resource")
                    assert resource in s.aggregates or resource in od_uris
                    aggregated_resources += 1
                if element.tag == SWORD + "originalDeposit":
                    resource = element.get(RDF + "resource")
                    assert resource in od_uris
                    original_deposits += 1
                if element.tag == SWORD + "state":
                    resource = element.get(RDF + "resource")
                    assert resource == "http://state/"
                    states += 1
                if element.tag == SWORD + "stateDescription":
                    assert element.text.strip() == "everything is groovy"
                    assert about == "http://state/"
                    state_descriptions += 1
                if element.tag == SWORD + "packaging":
                    resource = element.get(RDF + "resource")
                    assert resource == "http://package/"
                    assert about in od_uris
                    packaging += 1
                if element.tag == SWORD + "depositedOn":
                    assert about in od_uris
                    dep_on += 1
                if element.tag == SWORD + "depositedBy":
                    assert element.text in ["sword", "bob"]
                    assert about in od_uris
                    dep_by += 1
                if element.tag == SWORD + "depositedOnBehalfOf":
                    assert element.text == "obo"
                    assert about in od_uris
                    dep_obo += 1
        
        # now check that our counters/switches were flipped appropriately
        assert descriptions == 5
        assert states == 1
        assert state_descriptions == 1
        assert original_deposits == 2
        assert aggregated_resources == 4
        assert packaging == 2
        assert dep_on == 2
        assert dep_by == 2
        assert dep_obo == 1
        assert has_rem_description
        assert has_agg_description

    def test_04_rdf_aggregation_uri_exists(self):
        n = datetime.now()
        ods = [
            ("http://od1/", n, "http://package/", "sword", "obo"),
            ("http://192.168.23.133/asdfasd/datasets/mydataset6/example.zip", n, "http://package/", "bob", None)
        ]
        od_uris = ["http://od1/", "http://192.168.23.133/asdfasd/datasets/mydataset6/example.zip"]
        s = Statement(aggregation_uri="http://192.168.23.133/asdfasd/datasets/mydataset6", rem_uri="http://rem/",
                        original_deposits=ods,
                        aggregates=["http://od1/", "http://192.168.23.133/asdfasd/datasets/mydataset6/example.zip", "http://agg1/", "http://agg2/"],
                        states=[("http://state/", "everything is groovy")])
                        
        rdf_string = s.serialise_rdf(RDF_DOC)
        
        # first try the round trip
        rdf = etree.fromstring(rdf_string)
        
        # here are some counters/switches which will help us test that everything
        # is good within the statement
        descriptions = 0
        states = 0
        state_descriptions = 0
        original_deposits = 0
        aggregated_resources = 0
        packaging = 0
        dep_on = 0
        dep_by = 0
        dep_obo = 0
        
        has_rem_description = False
        has_agg_description = False
        ox_tag = False
        dc_tag = False
        rdf_tag = False
        
        # now go through the rdf and check that everything is as expected
        for desc in rdf.findall(RDF + "Description"):
            descriptions += 1
            about = desc.get(RDF + "about")
            for element in desc.getchildren():
                # we expect all of the same things to be true as in the previous
                # test
                if element.tag == ORE + "describes":
                    resource = element.get(RDF + "resource")
                    assert about == s.rem_uri
                    assert resource == s.aggregation_uri
                    has_rem_description = True
                if element.tag == ORE + "isDescribedBy":
                    resource = element.get(RDF + "resource")
                    assert about == s.aggregation_uri
                    assert resource == s.rem_uri
                    has_agg_description = True
                if element.tag == ORE + "aggregates":
                    resource = element.get(RDF + "resource")
                    assert resource in s.aggregates or resource in od_uris
                    aggregated_resources += 1
                if element.tag == SWORD + "originalDeposit":
                    resource = element.get(RDF + "resource")
                    assert resource in od_uris
                    original_deposits += 1
                if element.tag == SWORD + "state":
                    resource = element.get(RDF + "resource")
                    assert resource == "http://state/"
                    states += 1
                if element.tag == SWORD + "stateDescription":
                    assert element.text.strip() == "everything is groovy"
                    assert about == "http://state/"
                    state_descriptions += 1
                if element.tag == SWORD + "packaging":
                    resource = element.get(RDF + "resource")
                    assert resource == "http://package/"
                    assert about in od_uris
                    packaging += 1
                if element.tag == SWORD + "depositedOn":
                    assert about in od_uris
                    dep_on += 1
                if element.tag == SWORD + "depositedBy":
                    assert element.text in ["sword", "bob"]
                    assert about in od_uris
                    dep_by += 1
                if element.tag == SWORD + "depositedOnBehalfOf":
                    assert element.text == "obo"
                    assert about in od_uris
                    dep_obo += 1
                    
                # and we must verify that we didn't overwrite anything in the
                # passed in RDF document (don't check everything, but let's pick
                # one thing from each namespace)
                if element.tag == OX + "currentVersion":
                    assert element.text == "6"
                    ox_tag = True
                if element.tag == DC + "identifier":
                    assert element.text == "mydataset6"
                    dc_tag = True
                if element.tag == RDF + "type":
                    resource = element.get(RDF + "resource")
                    assert resource == "http://vocab.ox.ac.uk/dataset/schema#DataSet"
                    rdf_tag = True
        
        # now check that our counters/switches were flipped appropriately
        assert descriptions == 5
        assert states == 1
        assert state_descriptions == 1
        assert original_deposits == 2
        assert aggregated_resources == 4
        assert packaging == 2
        assert dep_on == 2
        assert dep_by == 2
        assert dep_obo == 1
        assert has_rem_description
        assert has_agg_description
        
        assert ox_tag
        assert dc_tag
        assert rdf_tag
        
    def test_05_rdf_no_aggregation(self):
        # FIXME: implement a test in which there is an existing RDF document
        # but it does not contain an rdf:Description@about which contains
        # the URI of an aggregation.  It should, therefore, simply add the
        # Statement to the existing rdf document
        pass
        
    def test_06_rdf_full_rem(self):
        # FIXME: impelement a test in which the existing RDF document is a full
        # ReM, and therefore the Statement is just additive.
        pass
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
