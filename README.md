SSS - Simple SWORD Server
=========================

Author: Richard Jones

Introduction
------------

The Simple Sword Server has to uses:

1/ It is a server library for python servers to use to be SWORDv2 compatible
2/ It is a stand-alone server which provides a reference implementation of the SWORD 2.0 specification

Prerequisites
-------------

SSS depends on web.py and lxml, so you will need to easy_install both of these before proceeding.  You will need to have installed libxml2 and libxslt1.1 for lxml to install.

Configuration
-------------

SSS has a configuration object which can be modified to change some aspects of its behaviour.  Open sss.py for
editing and find the Configuration object; each of the options available to you is documented inline.

If you are running this using the Quick Start below, you can leave the configuration as-is and everything should work.  If you are deploying SSS using web.py under Apache, you will need to change the configuration object from CherryPyConfiguration to ApacheConfiguration which can be done at the end of the file.


As a server library
===================

SSS provides an object model, two web API implementations (for web.py and pylons) and a server interface to be implemented to bind the SWORD API to the underlying server.

Implementing the Server API
---------------------------

The interface to be implemented by the server is sss.SwordServer.  This can then be configured in the sss.conf.json configuration file which is used by SSS to load as the implementation of the server.


Utilising the web.py web API
----------------------------

The Web.py API is in sss.webpy, and can only be run standalone.  This is the recommended usage of SSS for reference implementation (see below)


Utilising the pylons web API
----------------------------

The Pylons API is in sss.pylons_sword_controller, and can be imported into a Pylons project very easily.  You should create a new controller in your Pylons project, and have the body of that controller simply be:

    from sss.pylons_sword_controller import SwordController
    __controller__ = "SwordController"


As a Reference Implementation
=============================

When run as a reference implementation, SSS response to requests as if it were a real SWORD 2.0 server, although under the hood it is a simple file store which carries out minimal processing on the content it works with.

Quick Start
-----------

NOTE: using CherryPy out of the box does not support HTTP 1.1 (due to a bug), so you will need to issue requests with HTTP 1.0.  This is a nuisance, so for uses other than using CURL it is recommended to run SSS behind Apache, as described further down...


To start SSS using CherryPy, place sss.py in suitable directory of its own and start it with

    python sss.py

This will start the webserver at

    http://localhost:8080/

Note that SSS automatically creates a data store in the directory in which the sss.py file is located so this should
be done in a suitable directory.  To start the server on an alternative port (e.g. 8443) start it with

    python sss.py 8443


Deployment Under Apache
-----------------------

In order to get HTTP 1.1 support, it is necessary to deploy SSS under Apache (CherryPy does not support HTTP 1.1 at this point due to a bug)

To do this, you can follow the instructions at:

    http://webpy.org/cookbook/mod_wsgi-apache

When setting up your httpd.conf file, to allow file uploads to use Transfer-Encoding: chunked, and to ensure authorization credentials are forwarded, you will need to set up the configuration as follows:

    LoadModule wsgi_module /usr/lib/apache2/modules/mod_wsgi.so
    WSGIScriptAlias /sss /path/to/SSS/sss.py
    WSGIPassAuthorization On

    Alias /sss/static /path/to/SSS/static/
    AddType text/html .py

    <Directory /path/to/SSS/>
        WSGIChunkedRequest On 
        Order deny,allow
        Allow from all
    </Directory>

Note this sets an explicit location for the wsgi_module (required for Ubuntu, YMMV on other platforms), and adds the WSGIChunkedRequest to the correct context.


Requests to the server with CURL
--------------------------------

This section describes a series of CURL requests which utilise each part of the SWORD web service

Notice that for POST and PUT requests we use HTTP 1.0 for the curl requests.  This is because the CherryPy web server
which SSS operates under natively doesn't properly respond to those requests (although the functionality of the server
is unaffected).  You may find that programming against the SSS will require you to explicitly use HTTP 1.0 - this should
NOT be considered a requirement for SWORD 2.0.

###Authentication

To see the various authentication results, try the following requests on the service document.  By default SSS has the
following user details:

- user: sword
- password: sword
- On-Behalf-Of: obo

    curl -i http://sword:sword@localhost:8080/sd-uri

Successful authentication without an On-Behalf-Of user

    curl -i -H "X-On-Behalf-Of: obo" http://sword:sword@localhost:8080/sd-uri
    
Successful authentication with an On-Behalf-Of user

    curl -i http://localhost:8080/sd-uri
   
No Basic Auth credentials supplied, 401 Unauthorised response

    curl -i http://sword:drows@localhost:8080/sd-uri
    
Incorrect password, 401 unauthorised response

    curl -i http://drows:sword@localhost:8080/sd-uri
   
Incorrect user, 401 unauthorised response

    curl -i -H "X-On-Behalf-Of: bob" http://sword:sword@localhost:8080/sd-uri
   
Correct user but invalid On-Behalf-Of user, 401 unauthorised response

All subsequent requests can be done with an X-On-Behalf-Of header; no further examples will be provided

###Get the Service Document

HTTP: GET on SD-URI

    curl -i http://sword:sword@localhost:8080/sd-uri
    
This returns the Service Document with the configured number of collections listed

###Deposit some new content

HTTP: POST on Col-URI

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        sword:sword@[Col-URI]

This posts the example.zip file to the Col-URI with the filename "example.zip", and specifying that it is a zip
file.  Without the X-Packaging header this will be interpreted as a default SWORD package.  Col-URI should be obtained
from the Service Document.

This should return an HTTP status of 201 Created, and a Deposit Receipt

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "X-In-Progress: true"
        sword:sword@[Col-URI]

This should return an HTTP status of 202 Accepted, and a Deposit Receipt

    curl -i --http1.0 --data-binary "@multipart.dat"
        -H 'Content-Type: multipart/related; boundary="===============0670350989=="'
        -H "MIME-Version: 1.0"
        sword:sword@[Col-URI]

This will mimic an Atom Multipart deposit and will create two items in the container: atom.xml and example.xml (prefixed
with the current timestamp).  This should return an HTTP status of 201 Created and a Deposit Receipt.  You may add

    -H "X-In-Progress: true" to get a 202 Accepted back instead, as above.

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "X-Packaging: http://purl.org/net/sword/package/METSDSpaceSIP"
        sword:sword@[Col-URI]

This is an example using a different package format for the example.zip.  At the moment the ingest packager in SSS
will simply leave this package as it is, without attempting to unpack it

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "Content-MD5: 2b25f82ba67284461d4a481d7a06dd28"
        sword:sword[Col-URI]

This is an example where we provide the correct MD5 checksum for the item, just to demonstrate that this works with
or without the checksum.  See the section below on errors to supply incorrect checksums.

###List the contents of a Collection

HTTP: GET on Col-URI

    curl -i sword:sword@[Col-URI]

This will return an Atom Feed where each atom:entry refers to a collection in the specified collection.  This is
implemented only for the sake of convenience, so is not a full Feed; instead it just contains an atom:link element
containing the href to the Edit-URI for that Collection

###Get a representation of the container (Media Resource)

HTTP: GET on the Cont-URI or EM-URI

    curl -i [EM-URI]

Get the default dissemination package from the server.  In this case curl fills in the Accept header for us with "*/*".
This will return an application/zip file of all the content in the container.  Notice that this request does not
require authentication, as SSS models this as the public face of the content for the purposes of example.

FIXME: this method of content negotiation is under debate, although the SSS currently supports it

    curl -i -H "Accept: application/zip;swordpackage=http://www.swordapp.org/package/default" [EM-URI]

Explicitly request a zip file in the standard sword package format (which is, incidentally, a plain zip file)

    curl -i -H "Accept: application/zip" [EM-URI]

Explicitly request an ordinary zip file of the content (which happens to be no different from the standard sword package)

    curl -i -H "Accept: text/html" [EM-URI]

Explicitly request the HTML representation of the Media Resource.  This will return a 302 Found HTTP header with a
Location header which points to the HTML representation

    curl -i -H "Accept: application/vnd+msword" [EM-URI]

Generate a 415 Unsupported Media Type error

###Overwrite the existing Media Resource with a new one

HTTP: PUT on EM-URI

    curl -i -X PUT --http1.0 --data-binary "@example.zip"
       -H "Content-Disposition: filename=example.zip"
       -H "Content-Type: application/zip"
       sword:sword@[EM-URI]

This will replace all the existing content in the container identified with the EM-URI with the attached example.zip
file.  The package format is interpreted as the default sword package.  It will return a 201 Created and a Deposit
Receipt

    curl -i -X PUT --http1.0 --data-binary "@example.zip"
       -H "Content-Disposition: filename=example.zip"
       -H "Content-Type: application/zip"
       -H "X-In-Progress: true"
       sword:sword@[EM-URI]

This will do the same as above, but will return a 202 Accepted indicating that the update has been accepted into the
server, but has not yet been processed (for the purposes of example, obviously; it doesn't make any difference to
what actually happens on the server).

FIXME: this is not how AtomPub works, it instead says this should return a 200 - the jury is still out for SWORD on this

    curl -i -X PUT --http1.0 --data-binary "@example.zip"
       -H "Content-Disposition: filename=example.zip"
       -H "Content-Type: application/zip"
       -H "X-Suppress-Metadata: true"
       sword:sword@[EM-URI]

This would do the same as above but tells the server not to update the metadata of the item based on this deposit.  SSS
does not implement metadata updates for default packages which are not multipart, so this won't have any actual effect,
but it is a valid request.

    curl -i -X PUT --http1.0 --data-binary "@example.zip"
       -H "Content-Disposition: filename=example.zip"
       -H "Content-Type: application/zip"
       -H "X-Packaging: http://purl.org/net/sword/package/METSDSpaceSIP"
       sword:sword@[EM-URI]

An example of the same as above but with the X-Packaging header passed in.

###Delete the content but not the container

HTTP: DELETE on EM-URI

    curl -i -X DELETE sword:sword@[EM-URI]

This deletes all the content from the store, but not the container itself, and returns a 200 OK and a Deposit Receipt

###Get a representation of the container

HTTP: GET on Edit-URI

    curl -i sword:sword@[Edit-URI]

This retrieves the Edit-URI in its default format, which is as a copy of the Deposit Receipt - an atom entry document

    curl -i -H "Accept: application/rdf+xml" sword:sword@[Edit-URI]

This gives us the pure RDF/XML statement from the repository

    curl -i -H "Accept: application/atom+xml;type=entry" sword:sword@[Edit-URI]

This explicitly requests the Edit-URI in its atom entry form, which is the same as the default format

###Update a container by adding new content to the existing content

HTTP: POST on Edit-URI

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        sword:sword@[Edit-URI]

This adds the example.zip file to the server (notice that the Content-Disposition gives it the same name - SSS will
localise the names on receipt to avoid overwriting existing files) without removing any of the existing content.  This
will return a 201 Created (or if you add the X-In-Progress header a 202 Accepted) and the Deposit Receipt.

    curl -i --http1.0 --data-binary "@multipart.dat"
        -H 'Content-Type: multipart/related; boundary="===============0670350989=="'
        -H "MIME-Version: 1.0"
        sword:sword@[Edit-URI]

This will mimic an Atom Multipart deposit and will create two items in the container: atom.xml and example.xml (prefixed
with the current timestamp).  The atom.xml will overwrite any existing atom.xml file in this case, while the
example.zip will just be added under a localised name.  This should return an HTTP status of 201 Created and a Deposit
Receipt.  You may add -H "X-In-Progress: true" to get a 202 Accepted back instead, as above.

    curl -i --http1.0 --data-binary "@multipart.dat"
        -H 'Content-Type: multipart/related; boundary="===============0670350989=="'
        -H "MIME-Version: 1.0"
        -H "X-Suppress-Metadata: true"
        sword:sword@[Edit-URI]

This version of the request, with the X-Suppress-Metadata header set will do the same as above but it will not
attempt to extract any metadata from the atom.xml file as it would have done otherwise.

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "X-Packaging: http://purl.org/net/sword/package/METSDSpaceSIP"
        sword:sword@[Edit-URI]

###Delete the container and all its contents

HTTP: DELETE on Edit-URI

    curl -i -X DELETE sword:sword@[Edit-URI]

This will remove all the content from the container followed by the container itself.  It will return a 204 No Content
response with no response body.


###Generating Errors

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "X-Packaging: http://purl.org/net/sword/package/error"
        sword:sword[Col-URI]

Generates an ErrorContent error response on depositing a package whose package type doesn't match the X-Packaging
header

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "Content-MD5: 1234567890"
        sword:sword[Col-URI]

Generate an error for a mismatch between the checksum and the supplied checksum header, resulting in a 412 Precondition
Failed error.

    curl -i --http1.0 --data-binary "@example.zip"
        -H "Content-Disposition: filename=example.zip"
        -H "Content-Type: application/zip"
        -H "X-In-Progress: whatever"
        sword:sword[Col-URI]

Generate a Bad Request error by passing an illegal value to X-In-Progress, resulting in a 400 Bad Request response
