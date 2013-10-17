from mock import patch

from collections import OrderedDict

import cinder_utils as cinder_utils

from test_utils import (
    CharmTestCase,
)

TO_PATCH = [
    # helpers.core.hookenv
    'config',
    'log',
    # helpers.core.host
    'mounts',
    'umount',
    # ceph utils
    'ceph_create_pool',
    'ceph_pool_exists',
    # storage_utils
    'create_lvm_physical_volume',
    'create_lvm_volume_group',
    'deactivate_lvm_volume_group',
    'is_lvm_physical_volume',
    'relation_ids',
    'remove_lvm_physical_volume',
    'ensure_loopback_device',
    'is_block_device',
    'zap_disk',
]


MOUNTS = [
    ['/mnt', '/dev/vdb']
]


class TestCinderUtils(CharmTestCase):
    def setUp(self):
        super(TestCinderUtils, self).setUp(cinder_utils, TO_PATCH)
        self.config.side_effect = self.test_config.get_all

    def svc_enabled(self, svc):
        return svc in self.test_config.get('enabled-services')

    def test_all_services_enabled(self):
        '''It determines all services are enabled based on config'''
        self.test_config.set('enabled-services', 'all')
        enabled = []
        for s in ['volume', 'api', 'scheduler']:
            enabled.append(cinder_utils.service_enabled(s))
        self.assertEquals(enabled, [True, True, True])

    def test_service_enabled(self):
        '''It determines services are enabled based on config'''
        self.test_config.set('enabled-services', 'api,volume,scheduler')
        self.assertTrue(cinder_utils.service_enabled('volume'))

    def test_service_not_enabled(self):
        '''It determines services are not enabled based on config'''
        self.test_config.set('enabled-services', 'api,scheduler')
        self.assertFalse(cinder_utils.service_enabled('volume'))

    @patch('cinder_utils.service_enabled')
    def test_determine_packages_all(self, service_enabled):
        '''It determines all packages required when all services enabled'''
        service_enabled.return_value = True
        pkgs = cinder_utils.determine_packages()
        self.assertEquals(sorted(pkgs),
                          sorted(cinder_utils.COMMON_PACKAGES +
                                 cinder_utils.VOLUME_PACKAGES +
                                 cinder_utils.API_PACKAGES +
                                 cinder_utils.SCHEDULER_PACKAGES))

    @patch('cinder_utils.service_enabled')
    def test_determine_packages_subset(self, service_enabled):
        '''It determines packages required for a subset of enabled services'''
        service_enabled.side_effect = self.svc_enabled

        self.test_config.set('enabled-services', 'api')
        pkgs = cinder_utils.determine_packages()
        common = cinder_utils.COMMON_PACKAGES
        self.assertEquals(sorted(pkgs),
                          sorted(common + cinder_utils.API_PACKAGES))
        self.test_config.set('enabled-services', 'volume')
        pkgs = cinder_utils.determine_packages()
        common = cinder_utils.COMMON_PACKAGES
        self.assertEquals(sorted(pkgs),
                          sorted(common + cinder_utils.VOLUME_PACKAGES))
        self.test_config.set('enabled-services', 'api,scheduler')
        pkgs = cinder_utils.determine_packages()
        common = cinder_utils.COMMON_PACKAGES
        self.assertEquals(sorted(pkgs),
                          sorted(common + cinder_utils.API_PACKAGES +
                                 cinder_utils.SCHEDULER_PACKAGES))

    def test_creates_restart_map_all_enabled(self):
        '''It creates correct restart map when all services enabled'''
        ex_map = OrderedDict([
            ('/etc/cinder/cinder.conf', ['cinder-api', 'cinder-volume',
                                         'cinder-scheduler', 'haproxy']),
            ('/etc/cinder/api-paste.ini', ['cinder-api']),
            ('/etc/ceph/ceph.conf', ['cinder-volume']),
            ('/etc/haproxy/haproxy.cfg', ['haproxy']),
            ('/etc/apache2/sites-available/openstack_https_frontend',
             ['apache2']),
            ('/etc/apache2/sites-available/openstack_https_frontend.conf',
             ['apache2']),
        ])
        self.assertEquals(cinder_utils.restart_map(), ex_map)

    @patch('cinder_utils.service_enabled')
    def test_creates_restart_map_no_api(self, service_enabled):
        '''It creates correct restart map with api disabled'''
        service_enabled.side_effect = self.svc_enabled
        self.test_config.set('enabled-services', 'scheduler,volume')
        ex_map = OrderedDict([
            ('/etc/cinder/cinder.conf', ['cinder-volume', 'cinder-scheduler',
                                         'haproxy']),
            ('/etc/ceph/ceph.conf', ['cinder-volume']),
            ('/etc/haproxy/haproxy.cfg', ['haproxy']),
            ('/etc/apache2/sites-available/openstack_https_frontend',
             ['apache2']),
            ('/etc/apache2/sites-available/openstack_https_frontend.conf',
             ['apache2']),
        ])
        self.assertEquals(cinder_utils.restart_map(), ex_map)

    @patch('cinder_utils.service_enabled')
    def test_creates_restart_map_only_api(self, service_enabled):
        '''It creates correct restart map with only api enabled'''
        service_enabled.side_effect = self.svc_enabled
        self.test_config.set('enabled-services', 'api')
        ex_map = OrderedDict([
            ('/etc/cinder/cinder.conf', ['cinder-api', 'haproxy']),
            ('/etc/cinder/api-paste.ini', ['cinder-api']),
            ('/etc/haproxy/haproxy.cfg', ['haproxy']),
            ('/etc/apache2/sites-available/openstack_https_frontend',
             ['apache2']),
            ('/etc/apache2/sites-available/openstack_https_frontend.conf',
             ['apache2']),
        ])
        self.assertEquals(cinder_utils.restart_map(), ex_map)

    def test_ensure_block_device_bad_config(self):
        '''It doesn't prepare storage with bad config'''
        for none in ['None', 'none', None]:
            self.assertRaises(cinder_utils.CinderCharmError,
                              cinder_utils.ensure_block_device,
                              block_device=none)

    def test_ensure_block_device_loopback(self):
        '''It ensures loopback device when checking block device'''
        cinder_utils.ensure_block_device('/tmp/cinder.img')
        ex_size = cinder_utils.DEFAULT_LOOPBACK_SIZE
        self.ensure_loopback_device.assert_called_with('/tmp/cinder.img',
                                                       ex_size)

        cinder_utils.ensure_block_device('/tmp/cinder-2.img|15G')
        self.ensure_loopback_device.assert_called_with('/tmp/cinder-2.img',
                                                       '15G')

    def test_ensure_standard_block_device(self):
        '''It looks for storage at both relative and full device path'''
        for dev in ['vdb', '/dev/vdb']:
            cinder_utils.ensure_block_device(dev)
            self.is_block_device.assert_called_with('/dev/vdb')

    def test_ensure_nonexistent_block_device(self):
        '''It will not ensure a non-existant block device'''
        self.is_block_device.return_value = False
        self.assertRaises(cinder_utils.CinderCharmError,
                          cinder_utils.ensure_block_device, 'foo')

    def test_clean_storage_unmount(self):
        '''It unmounts block device when cleaning storage'''
        self.is_lvm_physical_volume.return_value = False
        self.zap_disk.return_value = True
        self.mounts.return_value = MOUNTS
        cinder_utils.clean_storage('/dev/vdb')
        self.umount.called_with('/dev/vdb', True)

    def test_clean_storage_lvm_wipe(self):
        '''It removes traces of LVM when cleaning storage'''
        self.mounts.return_value = []
        self.is_lvm_physical_volume.return_value = True
        cinder_utils.clean_storage('/dev/vdb')
        self.remove_lvm_physical_volume.assert_called_with('/dev/vdb')
        self.deactivate_lvm_volume_group.assert_called_with('/dev/vdb')

    def test_clean_storage_zap_disk(self):
        '''It removes traces of LVM when cleaning storage'''
        self.mounts.return_value = []
        self.is_lvm_physical_volume.return_value = False
        cinder_utils.clean_storage('/dev/vdb')
        self.zap_disk.assert_called_with('/dev/vdb')

    def test_prepare_lvm_storage_not_clean(self):
        '''It errors when prepping non-clean LVM storage'''
        self.is_lvm_physical_volume.return_value = True
        self.assertRaises(cinder_utils.CinderCharmError,
                          cinder_utils.prepare_lvm_storage,
                          block_device='/dev/foobar',
                          volume_group='bar-vg')

    def test_migrate_database(self):
        '''It migrates database with cinder-manage'''
        with patch('subprocess.check_call') as check_call:
            cinder_utils.migrate_database()
            check_call.assert_called_with(['cinder-manage', 'db', 'sync'])

    def test_ensure_ceph_pool(self):
        self.ceph_pool_exists.return_value = False
        cinder_utils.ensure_ceph_pool(service='cinder', replicas=3)
        self.ceph_create_pool.assert_called_with(service='cinder',
                                                 name='cinder',
                                                 replicas=3)

    def test_ensure_ceph_pool_already_exists(self):
        self.ceph_pool_exists.return_value = True
        cinder_utils.ensure_ceph_pool(service='cinder', replicas=3)
        self.assertFalse(self.ceph_create_pool.called)
