import hashlib, uuid

def md5_checksum(path):
    f = open(path, "r")
    m = hashlib.md5()
    m.update(f.read())
    digest = m.hexdigest()
    return digest

class CURL(object):

    def __init__(self, col_id=None, oid=None, user=None, password=None, obo_user=None,
                 base=None, binary=None, multipart=None, binary_content_type=None,
                 mime_boundary=None, package_format=None, checksum=None, sd_id=None,
                 accept=None, entry_doc=None, accept_media=None):
        # constant values
        self.cmd = "curl -i"
        self.post = "-X POST --http1.0"
        self.put = "-X PUT --http1.0"
        self.get = "-X GET"
        self.delete = "-X DELETE"
        self.http = "http://"
        self.on_behalf_of = "On-Behalf-Of"
        self.packaging = "Packaging"
        self.metadata_relevant = "Metadata-Relevant"
        self.in_progress = "In-Progress"
        self.data = "--data-binary"
        self.content_type = "Content-Type"
        self.content_disposition = "Content-Disposition"
        self.mime_version = "MIME-Version"
        self.content_md5 = "Content-MD5"
        self.accept_header = "Accept"
        self.accept_media_header = "Accept-Media-Features"
        self.slug_header = "Slug"
        self.sd_uri = "sd-uri"
        self.col_uri = "col-uri"
        self.em_uri = "em-uri"
        self.cont_uri = "cont-uri"
        self.edit_uri = "edit-uri"
        self.true_value = "true"
        self.false_value = "false"

        # parameters to be used
        self.user = "sword" if user is None else user
        self.password = "sword" if password is None else password
        self.base = "localhost:8080" if base is None else base
        self.obo_user = "obo" if obo_user is None else obo_user
        self.col_id = col_id # can be None
        self.oid = oid # can be None
        self.binary = "example.zip" if binary is None else binary
        self.multipart = "multipart.dat" if multipart is None else multipart
        self.entry_doc = "entry.xml" if entry_doc is None else entry_doc
        self.binary_content_type = "application/zip" if binary_content_type is None else binary_content_type
        self.mime_boundary = "===============0670350989==" if mime_boundary is None else mime_boundary
        self.package_format = "http://purl.org/net/sword/package/SimpleZip" if package_format is None else package_format
        self.checksum = "2b25f82ba67284461d4a481d7a06dd28" if checksum is None else checksum
        self.sd_id = sd_id # can be None
        self.accept = accept # can be None
        self.accept_media = accept_media # can be None

    def auth_url(self, type):
        auth_string = ""
        if self.user != "" and self.password != "":
            auth_string = self.user + ":" + self.password + "@"
        url = self.http + auth_string + self.base + "/" + type
        if self.col_id is not None:
            url += "/" + self.col_id
        if self.oid is not None and type != self.col_uri:
            url += "/" + self.oid
        if self.sd_id is not None:
            url += "/" + self.sd_id
        return url

    def header(self, key, value):
        return "-H '" + key + ": " + value + "'"

    def file_upload(self, multipart=False, atom_only=False):
        parts = [self.data]
        if atom_only:
            parts.append("\"@" + self.entry_doc + "\"")
        elif multipart:
            parts.append("\"@" + self.multipart + "\"")
        else:
            parts.append("\"@" + self.binary + "\"")

        return " ".join(parts)

    def get_content_disp(self, multipart=False, atom_only=False):
        if multipart or atom_only:
            return ""
        return self.header(self.content_disposition, "filename=" + self.binary)

    def get_content_type(self, multipart=False, atom_only=False):
        if atom_only:
            return self.header(self.content_type, "application/atom+xml;type=entry")
        elif multipart:
            t = "multipart/related; boundary=\"" + self.mime_boundary + "\""
            cth = self.header(self.content_type, t)
            mth = self.header(self.mime_version, "1.0")
            return cth + " " + mth
        else:
            return self.header(self.content_type, self.binary_content_type)

    def service_document(self, obo=False):
        parts = [self.cmd, self.get]
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        parts.append(self.auth_url(self.sd_uri))
        return " ".join(parts)

    def new_deposit(self, obo=False, in_progress=False, multipart=False, atom_only=False, checksum=False, metadata_relevant=False):
        parts = [self.cmd, self.post]
        parts.append(self.file_upload(multipart=multipart, atom_only=atom_only))
        parts.append(self.get_content_disp(multipart=multipart, atom_only=atom_only))
        parts.append(self.get_content_type(multipart=multipart, atom_only=atom_only))
        if not atom_only:
            parts.append(self.header(self.packaging, self.package_format))
        if self.oid:
            parts.append(self.header(self.slug_header, self.oid))
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        if in_progress:
            parts.append(self.header(self.in_progress, self.true_value))
        if checksum and not multipart:
            parts.append(self.header(self.content_md5, self.checksum))
        if metadata_relevant:
            parts.append(self.header(self.metadata_relevant, self.true_value))
        parts.append(self.auth_url(self.col_uri))
        return " ".join(parts)

    def list_collection(self, obo=True):
        parts = [self.cmd, self.get]
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        parts.append(self.auth_url(self.col_uri))
        return " ".join(parts)

    def media_resource(self, packaging=False):
        parts = [self.cmd, self.get]
        if self.accept is not None:
            parts.append(self.header(self.accept_header, self.accept))
        if self.package_format is not None and packaging:
            parts.append(self.header(self.packaging, self.package_format))
        parts.append(self.auth_url(self.cont_uri))
        return " ".join(parts)

    def overwrite(self, obo=False, in_progress=False, checksum=False, metadata_relevant=False):
        parts = [self.cmd, self.put]
        parts.append(self.file_upload(multipart=False))
        parts.append(self.get_content_disp(multipart=False))
        parts.append(self.get_content_type(multipart=False))
        parts.append(self.header(self.packaging, self.package_format))
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        if in_progress:
            parts.append(self.header(self.in_progress, self.true_value))
        if checksum:
            parts.append(self.header(self.content_md5, self.checksum))
        if metadata_relevant:
            parts.append(self.header(self.metadata_relevant, self.true_value))
        parts.append(self.auth_url(self.em_uri))
        return " ".join(parts)

    def delete_content(self, obo=False, in_progress=False):
        parts = [self.cmd, self.delete]
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        if in_progress:
            parts.append(self.header(self.in_progress, self.true_value))
        parts.append(self.auth_url(self.em_uri))
        return " ".join(parts)

    def get_container(self):
        parts = [self.cmd, self.get]
        if self.accept is not None:
            parts.append(self.header(self.accept_header, self.accept))
        parts.append(self.auth_url(self.edit_uri))
        return " ".join(parts)

    def update_metadata(self, obo=False, in_progress=False):
        parts = [self.cmd, self.put]
        parts.append(self.file_upload(atom_only=True))
        parts.append(self.get_content_type(atom_only=True))
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        if in_progress:
            parts.append(self.header(self.in_progress, self.true_value))
        parts.append(self.auth_url(self.edit_uri))
        return " ".join(parts)

    def deposit_additional(self, obo=False, in_progress=False, multipart=False, checksum=False, metadata_relevant=False, atom_only=False):
        parts = [self.cmd, self.post]
        parts.append(self.file_upload(multipart=multipart, atom_only=atom_only))
        if not atom_only:
            parts.append(self.get_content_disp(multipart=multipart))
        parts.append(self.get_content_type(multipart=multipart, atom_only=atom_only))
        if not atom_only:
            parts.append(self.header(self.packaging, self.package_format))
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        if in_progress:
            parts.append(self.header(self.in_progress, self.true_value))
        if checksum and not multipart:
            parts.append(self.header(self.content_md5, self.checksum))
        if metadata_relevant:
            parts.append(self.header(self.metadata_relevant, self.true_value))
        if multipart or atom_only:
            parts.append(self.auth_url(self.edit_uri))
        else:
            parts.append(self.auth_url(self.em_uri))
        
        return " ".join(parts)
        
    def replace(self, obo=False, in_progress=False, multipart=False, checksum=False, metadata_relevant=False, atom_only=False):
        parts = [self.cmd, self.put]
        parts.append(self.file_upload(multipart=multipart, atom_only=atom_only))
        if not atom_only:
            parts.append(self.get_content_disp(multipart=multipart))
        parts.append(self.get_content_type(multipart=multipart, atom_only=atom_only))
        if not atom_only:
            parts.append(self.header(self.packaging, self.package_format))
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        if in_progress:
            parts.append(self.header(self.in_progress, self.true_value))
        if checksum and not multipart:
            parts.append(self.header(self.content_md5, self.checksum))
        if metadata_relevant:
            parts.append(self.header(self.metadata_relevant, self.true_value))
        parts.append(self.auth_url(self.edit_uri))
        return " ".join(parts)

    def delete_container(self, obo=False):
        parts = [self.cmd, self.delete]
        if obo:
            parts.append(self.header(self.on_behalf_of, self.obo_user))
        parts.append(self.auth_url(self.edit_uri))
        return " ".join(parts)

def curl_batch(sid, cid, oid):

    # AUTHENTICATION
    ################

    print CURL().service_document()

    print CURL().service_document(obo=True)

    print CURL(user="", password="").service_document()

    print CURL(password="drows").service_document()

    print CURL(user="drows").service_document()

    print CURL(obo_user="bob").service_document(obo=True)

    # SERVICE DOCUMENTS
    ###################

    # Plain old service document
    print CURL().service_document()

    # sub service document with On-Behalf-Of header
    print CURL(sd_id=sid).service_document(obo=True)

    # DEPOSIT NEW CONTENT
    #####################

    # Most simple binary package deposit
    print CURL(col_id=cid).new_deposit()

    # Binary package deposit with In-Progress
    print CURL(col_id=cid).new_deposit(in_progress=True)

    # Atom Multipart deposit (most simple version)
    print CURL(col_id=cid).new_deposit(multipart=True)

    # Binary package deposit with custom packaging header
    print CURL(col_id=cid, package_format="http://purl.org/net/sword/package/METSDSpaceSIP").new_deposit()

    # Binary package deposit with checksum check
    print CURL(col_id=cid).new_deposit(checksum=True)

    # with a pre-prepared id
    print CURL(col_id=cid, oid=str(uuid.uuid4())).new_deposit()
    
    # Atom only
    print CURL(col_id=cid, oid=str(uuid.uuid4())).new_deposit(atom_only=True)

    # LIST A COLLECTION
    ###################

    print CURL(col_id=cid).list_collection()

    # GET THE MEDIA RESOURCE
    ########################

    print CURL(col_id=cid, oid=oid).media_resource()

    accept = "application/zip"
    package = "http://purl.org/net/sword/package/SimpleZip"
    print CURL(col_id=cid, oid=oid, accept=accept, package_format=package).media_resource(packaging=True)

    accept = "application/zip"
    print CURL(col_id=cid, oid=oid, accept=accept).media_resource()

    accept = "text/html"
    print CURL(col_id=cid, oid=oid, accept=accept).media_resource()

    accept = "application/vnd+msword"
    print CURL(col_id=cid, oid=oid, accept=accept).media_resource()
    
    accept = "application/xml+atom;type=feed"
    print CURL(col_id=cid, oid=oid, accept=accept).media_resource()

    # OVERWRITE THE EXISTING CONTENT
    ################################

    print CURL(col_id=cid, oid=oid).overwrite()

    print CURL(col_id=cid, oid=oid).overwrite(in_progress=True)

    print CURL(col_id=cid, oid=oid).overwrite(metadata_relevant=True)

    print CURL(col_id=cid, oid=oid, package_format="http://purl.org/net/sword/package/METSDSpaceSIP").overwrite()

    # DELETE THE CONTENT BUT NOT CONTAINER
    ######################################

    print CURL(col_id=cid, oid=oid).delete_content()

    print CURL(col_id=cid, oid=oid).delete_content(in_progress=True)

    # GET A REPRESENTATION OF THE CONTAINER
    #######################################

    print CURL(col_id=cid, oid=oid).get_container()

    # UPDATE THE CONTENT
    ####################

    print CURL(col_id=cid, oid=oid).deposit_additional()

    print CURL(col_id=cid, oid=oid).deposit_additional(in_progress=True)

    print CURL(col_id=cid, oid=oid).deposit_additional(checksum=True)

    print CURL(col_id=cid, oid=oid, package_format="http://purl.org/net/sword/package/METSDSpaceSIP").deposit_additional()
    
    print CURL(col_id=cid, oid=oid).deposit_additional(multipart=True)

    # ADD MORE METADATA
    ###################

    print CURL(col_id=cid, oid=oid).deposit_additional(atom_only=True)

    # UPDATE THE METADATA
    #####################

    print CURL(col_id=cid, oid=oid).update_metadata()

    print CURL(col_id=cid, oid=oid).update_metadata(in_progress=True)
    
    # REPLACE METADATA AND CONTENT
    ##############################
    
    print CURL(col_id=cid, oid=oid).replace(multipart=True)

    print CURL(col_id=cid, oid=oid).replace(multipart=True, metadata_relevant=True)

    # DELETE THE OBJECT
    ###################

    print CURL(col_id=cid, oid=oid).delete_container()

    # GENERATING ERRORS
    ###################

    print CURL(col_id=cid, package_format="http://purl.org/net/sword/package/error").new_deposit()

    print CURL(col_id=cid, checksum="1234567890").new_deposit(checksum=True)

    c = CURL(col_id=cid)
    c.true_value = "whatever"
    print c.new_deposit(in_progress=True)

    print CURL(obo_user="bob").service_document(obo=True)


from email.mime.multipart import MIMEMultipart, MIMEBase
import httplib, mimetypes
from email import encoders

def create_multipart_message(atom_file, binary_file, dat_file):

    # first build the full MIME message using the email library
    msg = MIMEMultipart("related")

    entry = open(atom_file, "rb")
    atom = MIMEBase("application", "atom+xml")
    atom['Content-Disposition'] = 'attachment; name="atom"'
    atom.set_payload(entry.read())
    msg.attach(atom)

    zip = open(binary_file, 'rb')
    base = MIMEBase("application", "zip")
    base['Content-Disposition'] = 'attachment; name="payload"; filename="example.zip"'
    base.set_payload(zip.read())
    encoders.encode_base64(base)
    msg.attach(base)

    # now, to make it work with HTTP pull out the main headers
    headers = {}
    header_mode = True
    body = []
    for line in msg.as_string().splitlines(True):
        if line == "\n" and header_mode:
            header_mode = False
        if header_mode:
            (key, value) = line.split(":", 1)
            headers[key.strip()] = value.strip()
        else:
            body.append(line)
    body = "".join(body)

    # write the body to the dat file
    o = open(dat_file, "wb")
    o.write(body)

    return headers

if __name__ == "__main__":
    sid = "subservice"
    cid = "37adfc78-ede6-462a-b3fa-eff948073f81"
    oid = "991f6fe8-545e-47d5-adeb-b06190e9eac3"
    curl_batch(sid, cid, oid)
