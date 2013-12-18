from mock import MagicMock, patch, call
from collections import OrderedDict
import charmhelpers.contrib.openstack.templating as templating
templating.OSConfigRenderer = MagicMock()
import horizon_utils as horizon_utils

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'get_os_codename_package',
    'config',
    'get_os_codename_install_source',
    'apt_update',
    'apt_install',
    'configure_installation_source',
    'log',
]


class TestHorizonUtils(CharmTestCase):
    def setUp(self):
        super(TestHorizonUtils, self).setUp(horizon_utils, TO_PATCH)

    @patch('subprocess.call')
    def test_enable_ssl(self, _call):
        horizon_utils.enable_ssl()
        _call.assert_has_calls([
            call(['a2ensite', 'default-ssl']),
            call(['a2enmod', 'ssl'])
        ])

    def test_restart_map(self):
        ex_map = OrderedDict([
            ('/etc/openstack-dashboard/local_settings.py', ['apache2']),
            ('/etc/apache2/conf.d/openstack-dashboard.conf', ['apache2']),
            ('/etc/apache2/conf-available/openstack-dashboard.conf',
             ['apache2']),
            ('/etc/apache2/sites-available/default-ssl', ['apache2']),
            ('/etc/apache2/sites-available/default', ['apache2']),
            ('/etc/apache2/ports.conf', ['apache2']),
            ('/etc/haproxy/haproxy.cfg', ['haproxy']),
        ])
        self.assertEquals(horizon_utils.restart_map(), ex_map)

    def test_do_openstack_upgrade(self):
        self.config.return_value = 'cloud:precise-havana'
        self.get_os_codename_install_source.return_value = 'havana'
        configs = MagicMock()
        horizon_utils.do_openstack_upgrade(configs)
        configs.set_release.assert_called_with(openstack_release='havana')
        self.log.assert_called()
        self.apt_update.assert_called_with(fatal=True)
        dpkg_opts = [
            '--option', 'Dpkg::Options::=--force-confnew',
            '--option', 'Dpkg::Options::=--force-confdef',
        ]
        self.apt_install.assert_called_with(packages=horizon_utils.PACKAGES,
                                            options=dpkg_opts, fatal=True)
        self.configure_installation_source.assert_called_with(
            'cloud:precise-havana'
        )

    @patch('os.path.exists')
    def test_register_configs(self, _exists):
        _exists.return_value = False
        self.get_os_codename_package.return_value = 'havana'
        configs = horizon_utils.register_configs()
        confs = [horizon_utils.LOCAL_SETTINGS,
                 horizon_utils.HAPROXY_CONF,
                 horizon_utils.APACHE_CONF,
                 horizon_utils.APACHE_SSL,
                 horizon_utils.APACHE_DEFAULT,
                 horizon_utils.PORTS_CONF]
        for conf in confs:
            configs.register.assert_any_call(
                conf,
                horizon_utils.CONFIG_FILES[conf]['hook_contexts']
            )

    @patch('os.path.exists')
    def test_register_configs_apache24(self, _exists):
        _exists.return_value = True
        self.get_os_codename_package.return_value = 'havana'
        configs = horizon_utils.register_configs()
        confs = [horizon_utils.LOCAL_SETTINGS,
                 horizon_utils.HAPROXY_CONF,
                 horizon_utils.APACHE_24_CONF,
                 horizon_utils.APACHE_SSL,
                 horizon_utils.APACHE_DEFAULT,
                 horizon_utils.PORTS_CONF]
        for conf in confs:
            configs.register.assert_any_call(
                conf,
                horizon_utils.CONFIG_FILES[conf]['hook_contexts']
            )

    @patch('os.path.exists')
    def test_register_configs_pre_install(self, _exists):
        _exists.return_value = False
        self.get_os_codename_package.return_value = None
        configs = horizon_utils.register_configs()
        confs = [horizon_utils.LOCAL_SETTINGS,
                 horizon_utils.HAPROXY_CONF,
                 horizon_utils.APACHE_CONF,
                 horizon_utils.APACHE_SSL,
                 horizon_utils.APACHE_DEFAULT,
                 horizon_utils.PORTS_CONF]
        for conf in confs:
            configs.register.assert_any_call(
                conf,
                horizon_utils.CONFIG_FILES[conf]['hook_contexts']
            )
