"""
client
======

Convenience functions for working with the Onshape API
"""

import mimetypes
import os
import random
import string
from time import sleep

from .onshape import Onshape


class Client:
    """
    Defines methods for testing the Onshape API. Comes with several methods:

    - Create a document
    - Delete a document
    - Get a list of documents

    Attributes:
        - stack (str, default='https://cad.onshape.com'): Base URL
        - logging (bool, default=True): Turn logging on or off
    """

    def __init__(self, stack='https://cad.onshape.com', logging=True, version=1, creds='./creds.json'):
        """
        Instantiates a new Onshape client.

        Args:
            - stack (str, default='https://cad.onshape.com'): Base URL
            - logging (bool, default=True): Turn logging on or off
        """

        self._stack = stack
        self._api = Onshape(stack=stack, creds=creds, logging=logging)
        self.version = version

    def new_document(self, name='Test Document', owner_type=0, public=False):
        """
        Create a new document.

        Args:
            - name (str, default='Test Document'): The doc name
            - owner_type (int, default=0): 0 for user, 1 for company, 2 for team
            - public (bool, default=False): Whether or not to make doc public

        Returns:
            - requests.Response: Onshape response data
        """

        payload = {'name': name, 'ownerType': owner_type, 'isPublic': public}

        return self._api.request('post', f'/api/v{self.version}/documents', body=payload)

    def new_fs(self, name, did, wid):
        """
        Create a new feature studio in the exisiting document.

        Args:
            - name (str, default='Test Document'): The doc name
            - owner_type (int, default=0): 0 for user, 1 for company, 2 for team
            - public (bool, default=False): Whether or not to make doc public

        Returns:
            - requests.Response: Onshape response data
        """

        payload = {
            'name': name,
        }

        return self._api.request('post', f'/api/v{self.version}/featurestudios/d/{did}/w/{wid}', body=payload)

    def get_fs_code(self, did, wid, eid):
        """
        Return feature studio code

        Args:
            - name (str, default='Test Document'): The doc name
            - owner_type (int, default=0): 0 for user, 1 for company, 2 for team
            - public (bool, default=False): Whether or not to make doc public

        Returns:
            - requests.Response: Onshape response data
        """

        return self._api.request('get', f'/api/v{self.version}/featurestudios/d/{did}/w/{wid}/e/{eid}')

    def get_fs_code_specs(self, did, wid, eid):
        """
        Return feature studio code

        Args:
            - name (str, default='Test Document'): The doc name
            - owner_type (int, default=0): 0 for user, 1 for company, 2 for team
            - public (bool, default=False): Whether or not to make doc public

        Returns:
            - requests.Response: Onshape response data
        """

        return self._api.request('get', f'/api/v{self.version}/featurestudios/d/{did}/w/{wid}/e/{eid}/featurespecs')

    def post_fs_code(self, did, wid, eid, content):
        """
        Writes feature studio code

        Args:
            - name (str, default='Test Document'): The doc name
            - owner_type (int, default=0): 0 for user, 1 for company, 2 for team
            - public (bool, default=False): Whether or not to make doc public

        Returns:
            - requests.Response: Onshape response data
        """
        payload = {'btType': 'BTFeatureStudioContents-2239', 'contents': content}
        return self._api.request('post', f'/api/v{self.version}/featurestudios/d/{did}/w/{wid}/e/{eid}', body=payload)

    def delete_element(self, did, wid, eid):
        """
        Writes feature studio code

        Args:
            - name (str, default='Test Document'): The doc name
            - owner_type (int, default=0): 0 for user, 1 for company, 2 for team
            - public (bool, default=False): Whether or not to make doc public

        Returns:
            - requests.Response: Onshape response data
        """
        return self._api.request('delete', f'/api/v{self.version}/elements/d/{did}/w/{wid}/e/{eid}')

    def rename_document(self, did, name):
        """
        Renames the specified document.

        Args:
            - did (str): Document ID
            - name (str): New document name

        Returns:
            - requests.Response: Onshape response data
        """

        payload = {'name': name}

        return self._api.request('post', f'/api/v{self.version}/documents/' + did, body=payload)

    def del_document(self, did):
        """
        Delete the specified document.

        Args:
            - did (str): Document ID

        Returns:
            - requests.Response: Onshape response data
        """

        return self._api.request('delete', f'/api/v{self.version}/documents/' + did)

    def get_document(self, did):
        """
        Get details for a specified document.

        Args:
            - did (str): Document ID

        Returns:
            - requests.Response: Onshape response data
        """

        return self._api.request('get', f'/api/v{self.version}/documents/' + did)

    def get_tabs(self, did, wid):
        """
        Retrieve tabs by documents id
        """
        return self._api.request('get', f'/api/v{self.version}/documents/d/' + did + '/w/' + wid + '/elements')

    def list_documents(self, offset: int = 0, sort: str = 'asc', sortColumn: str = 'CreatedAt', query: str = ''):
        """
        Get list of documents for current user.

        Args:
            - offset (int): [0, 10000]
            - sort (str): asc or desc
            - sortColumn (str): name | modifiedAt | createdAt | promotedAt
            - query (str): query to look for
        Returns:
            - requests.Response: Onshape response data
        """
        payload = {
            'offset': offset,
            'limit': 20,
            'sortOrder': sort,
            'sortColumn': sortColumn,
            'ownerType': 0,
            'filter': 4,
        }
        if query != '':
            payload['q'] = query

        return self._api.request('get', f'/api/v{self.version}/documents', query=payload)

    def create_assembly(self, did, wid, name='My Assembly'):
        """
        Creates a new assembly element in the specified document / workspace.

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - name (str, default='My Assembly')

        Returns:
            - requests.Response: Onshape response data
        """

        payload = {'name': name}

        return self._api.request('post', f'/api/v{self.version}/assemblies/d/' + did + '/w/' + wid, body=payload)

    def create_partstudio(self, did, wid, name='PS'):
        payload = {'name': name}
        return self._api.request('post', f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid, body=payload)

    def get_features(self, did, wid, eid):
        """
        Gets the feature list for specified document / workspace / part studio.

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID

        Returns:
            - requests.Response: Onshape response data
        """

        return self._api.request(
            'get', f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/features'
        )

    def add_feature(self, did, wid, eid, feature):
        """
        Gets the feature list for specified document / workspace / part studio.

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID

        Returns:
            - requests.Response: Onshape response data
        """
        payload = {'btType': 'BTFeatureDefinitionCall-1406', 'feature': feature}
        return self._api.request(
            'post',
            f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/features',
            body=payload,
            timeout=120,
        )

    def delete_feature(self, did, wid, eid, fid):
        return self._api.request(
            'delete',
            f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/features/featureid/' + fid,
        )

    def get_partstudio_tessellatededges(self, did, wid, eid):
        """
        Gets the tessellation of the edges of all parts in a part studio.

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID

        Returns:
            - requests.Response: Onshape response data
        """

        return self._api.request(
            'get', f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/tessellatededges'
        )

    def get_sketch_information(self, did, wid, eid):
        """
        Gets the parameters for all sketches

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID

        Returns:
            - requests.Response: Onshape response data
        """
        query = {
            'output3D': False,
            'curvePoints': True,
            'includeGeometry': True,
        }
        return self._api.request(
            'get', f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/sketches', query=query
        )

    def upload_blob(self, did, wid, filepath='./blob.json'):
        """
        Uploads a file to a new blob element in the specified doc.

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - filepath (str, default='./blob.json'): Blob element location

        Returns:
            - requests.Response: Onshape response data
        """

        chars = string.ascii_letters + string.digits
        boundary_key = ''.join(random.choice(chars) for i in range(8))

        mimetype = mimetypes.guess_type(filepath)[0]
        encoded_filename = os.path.basename(filepath)
        file_content_length = str(os.path.getsize(filepath))
        blob = open(filepath)

        req_headers = {'Content-Type': 'multipart/form-data; boundary="%s"' % boundary_key}

        # build request body
        payload = '--' + boundary_key + '\r\nContent-Disposition: form-data; name="encodedFilename"\r\n\r\n'
        payload += encoded_filename + '\r\n'
        payload += '--' + boundary_key + '\r\nContent-Disposition: form-data; name="fileContentLength"\r\n\r\n'
        payload += file_content_length + '\r\n'
        payload += '--' + boundary_key + '\r\nContent-Disposition: form-data; name="file"; filename="'
        payload += encoded_filename + '"\r\n'
        payload += 'Content-Type: ' + mimetype + '\r\n\r\n'
        payload += blob.read()
        payload += '\r\n--' + boundary_key + '--'

        return self._api.request(
            'post', f'/api/v{self.version}/blobelements/d/' + did + '/w/' + wid, headers=req_headers, body=payload
        )

    def part_studio_stl(self, did, wid, eid):
        """
        Exports STL export from a part studio

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID

        Returns:
            - requests.Response: Onshape response data
        """

        req_headers = {'Accept': 'application/vnd.onshape.v1+octet-stream'}
        return self._api.request(
            'get',
            f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/stl',
            headers=req_headers,
        )

    def get_translation(self, tid):
        return self._api.request('get', f'/api/v{self.version}/translations/' + tid)

    def export_step(self, did, wid, eid):
        payload = {
            # main params
            'destinationName': 'tmp_name',
            'grouping': True,
            'storeInDocument': False,
            # other params
            'includeExportIds': False,
            'isYAxisUp': False,
            'notifyUser': True,
            'stepParasolidPreprocessingOption': 'NO_PRE_PROCESSING',
            'stepUnit': 'METER',
        }
        # Create translation request
        res = self._api.request(
            'post',
            f'/api/v{self.version}/partstudios/d/' + did + '/w/' + wid + '/e/' + eid + '/export/step',
            body=payload,
        )
        requests_remains = int(res.headers.get('X-Rate-Limit-Remaining', 0))
        if res.status_code != 200:
            return None, requests_remains
        # Wait until file is ready
        tid = res.json()['id']
        res = self.get_translation(tid).json()
        total_time = 0
        time_out = 1  # sec.
        while res['requestState'] != 'DONE':
            total_time += time_out
            if total_time == 10:
                print('download timeout > 10 sec')
                time_out = 2
            elif total_time == 30:
                print('download timeout > 30 sec')
                time_out = 5
            elif total_time == 60:
                print('download timeout > 60 sec')
                return None, requests_remains
            sleep(time_out)
            res = self.get_translation(tid).json()
        # Download created step
        external_id = res['resultExternalDataIds'][0]
        step_model = self._api.request('get', f'/api/v{self.version}/documents/d/{did}/externaldata/{external_id}')
        return step_model, requests_remains
