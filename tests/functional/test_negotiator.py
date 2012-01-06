import os

from . import TestController

from sss.negotiator import AcceptParameters, ContentType, ContentNegotiator, Language

class TestEntry(TestController):

    # Content Type Only Tests
    #########################

    def test_01_content_type_only_text_plain(self):
        accept = "text/plain"
        server = [AcceptParameters(ContentType("text/plain"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "text/plain"
    
    def test_02_content_type_only_xml_vs_rdf_no_q(self):
        accept = "application/atom+xml, application/rdf+xml"
        server = [AcceptParameters(ContentType("application/rdf+xml")), AcceptParameters(ContentType("application/atom+xml"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "application/atom+xml"
    
    def test_03_content_type_only_xml_vs_rdf_with_q(self):
        accept = "application/atom+xml;q=0.6, application/rdf+xml;q=0.9"
        server = [AcceptParameters(ContentType("application/rdf+xml")), AcceptParameters(ContentType("application/atom+xml"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "application/rdf+xml"

    def test_04_content_type_only_xml_vs_rdf_vs_html_with_mixed_q(self):
        accept = "application/atom+xml;q=0.6, application/rdf+xml;q=0.9, text/html"
        server = [AcceptParameters(ContentType("application/rdf+xml")), AcceptParameters(ContentType("application/atom+xml")),
                    AcceptParameters(ContentType("text/html"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "text/html"
        
    def test_05_content_type_only_text_plain_unsupported(self):
        accept = "text/plain"
        server = [AcceptParameters(ContentType("text/html"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap is None
        
    def test_06_content_type_only_atom_vs_rdf_html_mixed_q_preferred_unavailable(self):
        accept = "application/atom+xml;q=0.6, application/rdf+xml;q=0.9, text/html"
        server = [AcceptParameters(ContentType("application/rdf+xml")), AcceptParameters(ContentType("application/atom+xml"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "application/rdf+xml"
        
    def test_07_content_type_only_atom_vs_rdf_html_mixed_q_preferred_available(self):
        accept = "application/atom+xml;q=0.6, application/rdf+xml;q=0.9, text/html"
        server = [AcceptParameters(ContentType("application/rdf+xml")), AcceptParameters(ContentType("text/html"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "text/html"
        
    def test_08_content_type_with_param_supported(self):
        accept = "application/atom+xml;type=feed"
        server = [AcceptParameters(ContentType("application/atom+xml;type=feed"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "application/atom+xml;type=feed"
        
    def test_09_content_type_with_wildcard_supported(self):
        accept = "image/*"
        server = [AcceptParameters(ContentType("text/plain")), AcceptParameters(ContentType("image/png")),
                    AcceptParameters(ContentType("image/jpeg"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "image/png"
        
    def test_10_content_type_full_wildcard(self):
        accept = "*/*"
        server = [AcceptParameters(ContentType("text/plain")), AcceptParameters(ContentType("image/png")),
                    AcceptParameters(ContentType("image/jpeg"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept)
        assert ap.content_type.mimetype() == "text/plain"
    
    # Language Only Tests
    #####################
    
    def test_11_language_en(self):
        accept_language = "en"
        server = [AcceptParameters(language=Language("en"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept_language)
        assert ap.language == "en"
        
    def test_12_language_en_vs_de_no_q(self):
        accept = "en, de"
        server = [AcceptParameters(language=Language("en")), AcceptParameters(language=Language("de"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "en"
        
    def test_13_language_fr_vs_no_with_q(self):
        accept = "fr;q=0.7, no;q=0.8"
        server = [AcceptParameters(language=Language("fr")), AcceptParameters(language=Language("no"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "no"
        
    def test_14_language_en_vs_de_vs_fr_mixed_q(self):
        accept = "en;q=0.6, de;q=0.9, fr"
        server = [AcceptParameters(language=Language("en")), AcceptParameters(language=Language("de")),
                    AcceptParameters(language=Language("fr"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "fr"
    
    def test_15_language_en_unsupported(self):
        accept = "en;q=0.6, de;q=0.9, fr"
        accept = "en"
        server = [AcceptParameters(language=Language("de"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap is None
        
    def test_16_language_en_vs_no_vs_de_mixed_q_preferred_unavailable(self):
        accept = "en;q=0.6, no;q=0.9, de"
        server = [AcceptParameters(language=Language("en")), AcceptParameters(language=Language("no"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "no"
        
    def test_17_language_en_vs_no_vs_de_mixed_q_preferred_available(self):
        accept = "en;q=0.6, no;q=0.9, de"
        server = [AcceptParameters(language=Language("no")), AcceptParameters(language=Language("de"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "de"
        
    def test_18_language_en_gb_supported(self):
        accept = "en-gb"
        server = [AcceptParameters(language=Language("en-gb"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "en-gb"
        
    def test_19_language_en_gb_unsupported(self):
        accept = "en-gb"
        server = [AcceptParameters(language=Language("en"))]
        cn = ContentNegotiator(acceptable=server, ignore_language_variants=False)
        ap = cn.negotiate(accept_language=accept)
        assert ap is None
        
    def test_20_language_en_gb_supported_by_language_variant(self):
        accept = "en-gb"
        server = [AcceptParameters(language=Language("en"))]
        cn = ContentNegotiator(acceptable=server, ignore_language_variants=True)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "en"
        
    def test_21_language_en_partially_supported(self):
        accept = "en"
        server = [AcceptParameters(language=Language("en-gb"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "en-gb"
        
    def test_22_language_wildcard_alone(self):
        accept = "*"
        server = [AcceptParameters(language=Language("no")), AcceptParameters(language=Language("de"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "no"
        
    def test_23_language_en_plus_wildcard_primary_unsupported(self):
        accept = "en, *"
        server = [AcceptParameters(language=Language("no")), AcceptParameters(language=Language("de"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "no"
        
    def test_24_language_en_plus_wildcard_primary_supported(self):
        accept = "en, *"
        server = [AcceptParameters(language=Language("en")), AcceptParameters(language=Language("de"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_language=accept)
        assert ap.language == "en"
    
    # Packaging Only Tests
    ######################
    
    def test_25_packaging_supported(self):
        accept = "http://whatever/"
        server = [AcceptParameters(packaging="http://whatever/")]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_packaging=accept)
        assert ap.packaging == "http://whatever/"
        
    def test_26_packaging_unsupported(self):
        accept = "http://whatever/"
        server = [AcceptParameters(packaging="http://other/")]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_packaging=accept)
        assert ap is None
        
    def test_27_packaging_supported_many_options(self):
        accept = "http://whatever/"
        server = [AcceptParameters(packaging="http://other/"), AcceptParameters(packaging="http://whatever/")]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept_packaging=accept)
        assert ap.packaging == "http://whatever/"
    
    # Language + Content Type tests
    ###############################
    
    def test_28_content_type_language(self):
        accept = "text/html"
        accept_lang = "en"
        server = [AcceptParameters(ContentType("text/html"), Language("en"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept, accept_language=accept_lang)
        assert ap.language == "en"
        assert ap.content_type.mimetype() == "text/html"
        
    def test_29_content_types_language(self):
        accept = "text/html, text/plain"
        accept_lang = "en"
        server = [AcceptParameters(ContentType("text/html"), Language("de")), AcceptParameters(ContentType("text/plain"), Language("en"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept, accept_language=accept_lang)
        assert ap.language == "en"
        assert ap.content_type.mimetype() == "text/plain"
        
    def test_30_content_types_languages(self):
        accept = "text/html, text/plain"
        accept_lang = "en, de"
        server = [AcceptParameters(ContentType("text/html"), Language("de")), AcceptParameters(ContentType("text/plain"), Language("en"))]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept, accept_language=accept_lang)
        assert ap.language == "de"
        assert ap.content_type.mimetype() == "text/html"
        
    def test_31_content_types_language_weights(self):
        weights = {'content_type' : 2.0, 'language' : 1.0, 'charset' : 1.0, 'encoding' : 1.0}
        accept = "text/html, text/plain"
        accept_lang = "en"
        server = [AcceptParameters(ContentType("text/html"), Language("de")), AcceptParameters(ContentType("text/plain"), Language("en"))]
        cn = ContentNegotiator(acceptable=server, weights=weights)
        ap = cn.negotiate(accept=accept, accept_language=accept_lang)
        assert ap.language == "en"
        assert ap.content_type.mimetype() == "text/plain"
    
    # Content Type and Packaging tests
    ##################################
    
    def test_32_content_type_packaging(self):
        accept = "application/zip"
        accept_packaging = "packaging:BagIt"
        server = [AcceptParameters(ContentType("application/zip"), packaging=accept_packaging)]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept, accept_packaging=accept_packaging)
        assert ap.content_type.mimetype() == "application/zip"
        assert ap.packaging == "packaging:BagIt"
        
    def test_33_content_types_packaging(self):
        accept = "application/zip, application/tar"
        accept_packaging = "packaging:BagIt"
        server = [AcceptParameters(ContentType("application/tar"), packaging=accept_packaging)]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept, accept_packaging=accept_packaging)
        assert ap.content_type.mimetype() == "application/tar"
        assert ap.packaging == "packaging:BagIt"
        
    def test_34_content_types_packaging_weights(self):
        weights = {'content_type' : 2.0, 'packaging' : 0.5}
        accept = "application/zip, application/tar"
        accept_packaging = "packaging:BagIt"
        server = [AcceptParameters(ContentType("application/tar"), packaging=accept_packaging), 
                    AcceptParameters(ContentType("application/zip"), packaging="http://other/")]
        cn = ContentNegotiator(acceptable=server)
        ap = cn.negotiate(accept=accept, accept_packaging=accept_packaging)
        assert ap.content_type.mimetype() == "application/tar"
        assert ap.packaging == "packaging:BagIt"
    
