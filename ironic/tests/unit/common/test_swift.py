# Copyright 2013 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import mock
from oslo_config import cfg
import six
from six.moves import builtins as __builtin__
from swiftclient import client as swift_client
from swiftclient import exceptions as swift_exception
from swiftclient import utils as swift_utils

from ironic.common import exception
from ironic.common import swift
from ironic.tests import base

CONF = cfg.CONF

if six.PY3:
    import io
    file = io.BytesIO


@mock.patch.object(swift_client, 'Connection', autospec=True)
class SwiftTestCase(base.TestCase):

    def setUp(self):
        super(SwiftTestCase, self).setUp()
        self.swift_exception = swift_exception.ClientException('', '')

        self.config(admin_user='admin', group='keystone_authtoken')
        self.config(admin_tenant_name='tenant', group='keystone_authtoken')
        self.config(admin_password='password', group='keystone_authtoken')
        self.config(auth_uri='http://authurl', group='keystone_authtoken')
        self.config(auth_version='2', group='keystone_authtoken')
        self.config(swift_max_retries=2, group='swift')
        self.config(insecure=0, group='keystone_authtoken')
        self.config(cafile='/path/to/ca/file', group='keystone_authtoken')

    def test___init__(self, connection_mock):
        swift.SwiftAPI()
        params = {'retries': 2,
                  'insecure': 0,
                  'user': 'admin',
                  'tenant_name': 'tenant',
                  'key': 'password',
                  'authurl': 'http://authurl/v2.0',
                  'cacert': '/path/to/ca/file',
                  'auth_version': '2'}
        connection_mock.assert_called_once_with(**params)

    @mock.patch.object(__builtin__, 'open', autospec=True)
    def test_create_object(self, open_mock, connection_mock):
        swiftapi = swift.SwiftAPI()
        connection_obj_mock = connection_mock.return_value
        mock_file_handle = mock.MagicMock(spec=file)
        mock_file_handle.__enter__.return_value = 'file-object'
        open_mock.return_value = mock_file_handle

        connection_obj_mock.put_object.return_value = 'object-uuid'

        object_uuid = swiftapi.create_object('container', 'object',
                                             'some-file-location')

        connection_obj_mock.put_container.assert_called_once_with('container')
        connection_obj_mock.put_object.assert_called_once_with(
            'container', 'object', 'file-object', headers=None)
        self.assertEqual('object-uuid', object_uuid)

    @mock.patch.object(__builtin__, 'open', autospec=True)
    def test_create_object_create_container_fails(self, open_mock,
                                                  connection_mock):
        swiftapi = swift.SwiftAPI()
        connection_obj_mock = connection_mock.return_value
        connection_obj_mock.put_container.side_effect = self.swift_exception
        self.assertRaises(exception.SwiftOperationError,
                          swiftapi.create_object, 'container',
                          'object', 'some-file-location')
        connection_obj_mock.put_container.assert_called_once_with('container')
        self.assertFalse(connection_obj_mock.put_object.called)

    @mock.patch.object(__builtin__, 'open', autospec=True)
    def test_create_object_put_object_fails(self, open_mock, connection_mock):
        swiftapi = swift.SwiftAPI()
        mock_file_handle = mock.MagicMock(spec=file)
        mock_file_handle.__enter__.return_value = 'file-object'
        open_mock.return_value = mock_file_handle
        connection_obj_mock = connection_mock.return_value
        connection_obj_mock.head_account.side_effect = None
        connection_obj_mock.put_object.side_effect = self.swift_exception
        self.assertRaises(exception.SwiftOperationError,
                          swiftapi.create_object, 'container',
                          'object', 'some-file-location')
        connection_obj_mock.put_container.assert_called_once_with('container')
        connection_obj_mock.put_object.assert_called_once_with(
            'container', 'object', 'file-object', headers=None)

    @mock.patch.object(swift_utils, 'generate_temp_url', autospec=True)
    def test_get_temp_url(self, gen_temp_url_mock, connection_mock):
        swiftapi = swift.SwiftAPI()
        connection_obj_mock = connection_mock.return_value
        auth = ['http://host/v1/AUTH_tenant_id', 'token']
        connection_obj_mock.get_auth.return_value = auth
        head_ret_val = {'x-account-meta-temp-url-key': 'secretkey'}
        connection_obj_mock.head_account.return_value = head_ret_val
        gen_temp_url_mock.return_value = 'temp-url-path'
        temp_url_returned = swiftapi.get_temp_url('container', 'object', 10)
        connection_obj_mock.get_auth.assert_called_once_with()
        connection_obj_mock.head_account.assert_called_once_with()
        object_path_expected = '/v1/AUTH_tenant_id/container/object'
        gen_temp_url_mock.assert_called_once_with(object_path_expected, 10,
                                                  'secretkey', 'GET')
        self.assertEqual('http://host/temp-url-path', temp_url_returned)

    def test_delete_object(self, connection_mock):
        swiftapi = swift.SwiftAPI()
        connection_obj_mock = connection_mock.return_value
        swiftapi.delete_object('container', 'object')
        connection_obj_mock.delete_object.assert_called_once_with('container',
                                                                  'object')

    def test_delete_object_exc_resource_not_found(self, connection_mock):
        swiftapi = swift.SwiftAPI()
        exc = swift_exception.ClientException("Resource not found",
                                              http_status=404)
        connection_obj_mock = connection_mock.return_value
        connection_obj_mock.delete_object.side_effect = exc
        self.assertRaises(exception.SwiftObjectNotFoundError,
                          swiftapi.delete_object, 'container', 'object')
        connection_obj_mock.delete_object.assert_called_once_with('container',
                                                                  'object')

    def test_delete_object_exc(self, connection_mock):
        swiftapi = swift.SwiftAPI()
        exc = swift_exception.ClientException("Operation error")
        connection_obj_mock = connection_mock.return_value
        connection_obj_mock.delete_object.side_effect = exc
        self.assertRaises(exception.SwiftOperationError,
                          swiftapi.delete_object, 'container', 'object')
        connection_obj_mock.delete_object.assert_called_once_with('container',
                                                                  'object')

    def test_head_object(self, connection_mock):
        swiftapi = swift.SwiftAPI()
        connection_obj_mock = connection_mock.return_value
        expected_head_result = {'a': 'b'}
        connection_obj_mock.head_object.return_value = expected_head_result
        actual_head_result = swiftapi.head_object('container', 'object')
        connection_obj_mock.head_object.assert_called_once_with('container',
                                                                'object')
        self.assertEqual(expected_head_result, actual_head_result)

    def test_update_object_meta(self, connection_mock):
        swiftapi = swift.SwiftAPI()
        connection_obj_mock = connection_mock.return_value
        headers = {'a': 'b'}
        swiftapi.update_object_meta('container', 'object', headers)
        connection_obj_mock.post_object.assert_called_once_with(
            'container', 'object', headers)
