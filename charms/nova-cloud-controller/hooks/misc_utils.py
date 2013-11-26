# TODO: Promote all of this to charm-helpers, its shared with nova-compute

from charmhelpers.core.hookenv import (
    config,
    log,
    relation_get,
    unit_private_ip,
    ERROR,
)

from charmhelpers.contrib.openstack import context

from charmhelpers.fetch import apt_install, filter_installed_packages

from charmhelpers.contrib.openstack.utils import os_release


def _save_flag_file(path, data):
    '''
    Saves local state about plugin or manager to specified file.
    '''
    # Wonder if we can move away from this now?
    with open(path, 'wb') as out:
        out.write(data)


class NeutronContext(object):
    interfaces = []

    @property
    def plugin(self):
        return None

    @property
    def network_manager(self):
        return network_manager()

    @property
    def packages(self):
        return network_plugin_attribute(self.plugin, 'packages')

    @property
    def neutron_security_groups(self):
        return None

    def _ensure_packages(self):
        '''Install but do not upgrade required plugin packages'''
        required = filter_installed_packages(self.packages)
        if required:
            apt_install(required, fatal=True)

    def ovs_ctxt(self):
        ovs_ctxt = {
            'neutron_plugin': 'ovs',
            # quantum.conf
            'core_plugin': network_plugin_attribute(self.plugin, 'driver'),
            # NOTE: network api class in template for each release.
            # nova.conf
            #'libvirt_vif_driver': n_driver,
            #'libvirt_use_virtio_for_bridges': True,
            # ovs config
            'local_ip': unit_private_ip(),
        }

        if self.neutron_security_groups:
            ovs_ctxt['neutron_security_groups'] = True

        return ovs_ctxt

    def n1kv_ctxt(self):
        n1kv_ctxt = {
            'neutron_plugin': 'n1kv',
            # quantum.conf
            'core_plugin': network_plugin_attribute(self.plugin, 'driver'),
            # NOTE: network api class in template for each release.
            # nova.conf
            #'libvirt_vif_driver': n_driver,
            #'libvirt_use_virtio_for_bridges': True,
            # ovs config
            'local_ip': unit_private_ip(),
        }

        if self.neutron_security_groups:
            n1kv_ctxt['neutron_security_groups'] = True

        return n1kv_ctxt

    def __call__(self):

        if self.network_manager not in ['quantum', 'neutron']:
            return {}

        if not self.plugin:
            return {}

        self._ensure_packages()

        ctxt = {'network_manager': self.network_manager}

        if self.plugin == 'ovs':
            ctxt.update(self.ovs_ctxt())

        if self.plugin == 'n1kv':
            ctxt.update(self.n1kv_ctxt())

        _save_flag_file(path='/etc/nova/quantum_plugin.conf', data=self.plugin)
        _save_flag_file(path='/etc/nova/neutron_plugin.conf', data=self.plugin)
        return ctxt


class NeutronComputeContext(NeutronContext):
    interfaces = []

    @property
    def plugin(self):
        return relation_get('neutron_plugin') or relation_get('quantum_plugin')

    @property
    def network_manager(self):
        return relation_get('network_manager')

    @property
    def neutron_security_groups(self):
        groups = [relation_get('neutron_security_groups'),
                  relation_get('quantum_security_groups')]
        return ('yes' in groups or 'Yes' in groups)

    def ovs_ctxt(self):
        ctxt = super(NeutronComputeContext, self).ovs_ctxt()
        if os_release('nova-common') == 'folsom':
            n_driver = 'nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver'
        else:
            n_driver = 'nova.virt.libvirt.vif.LibvirtGenericVIFDriver'
        ctxt.update({
            'libvirt_vif_driver': n_driver,
        })
        return ctxt

    def n1kv_ctxt(self):
        ctxt = super(NeutronComputeContext, self).n1kv_ctxt()
        if os_release('nova-common') == 'folsom':
            n_driver = 'nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver'
        else:
            n_driver = 'nova.virt.libvirt.vif.LibvirtGenericVIFDriver'
        ctxt.update({
            'libvirt_vif_driver': n_driver,
        })
        return ctxt
class NeutronCCContext(NeutronContext):
    interfaces = []

    @property
    def plugin(self):
        return neutron_plugin()

    @property
    def network_manager(self):
        return network_manager()

    @property
    def neutron_security_groups(self):
        sec_groups = (config('neutron-security-groups') or
                      config('quantum-security-groups'))
        return sec_groups.lower() == 'yes'


# legacy
def quantum_plugins():
    return {
        'ovs': {
            'config': '/etc/quantum/plugins/openvswitch/'
                      'ovs_quantum_plugin.ini',
            'driver': 'quantum.plugins.openvswitch.ovs_quantum_plugin.'
                      'OVSQuantumPluginV2',
            'contexts': [
                NeutronContext(),
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron')],
            'services': ['quantum-plugin-openvswitch-agent'],
            'packages': ['quantum-plugin-openvswitch-agent',
                         'openvswitch-datapath-dkms'],
        },
        'nvp': {
            'config': '/etc/quantum/plugins/nicira/nvp.ini',
            'driver': 'quantum.plugins.nicira.nicira_nvp_plugin.'
                      'QuantumPlugin.NvpPluginV2',
            'services': [],
            'packages': ['quantum-plugin-nicira'],
        },
        'n1kv': {
            'config': '/etc/quantum/plugins/cisco/cisco_plugins.ini',
            'driver': 'quantum.plugins.cisco.network_plugin.PluginV2',
            'contexts': [
                NeutronContext(),
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron')],
            'services': ['quantum-plugin-cisco'],
            'packages': [['quantum-plugin-cisco']],
        }
    }


def neutron_plugins():
    return {
        'ovs': {
            'config': '/etc/neutron/plugins/openvswitch/'
                      'ovs_neutron_plugin.ini',
            'driver': 'neutron.plugins.openvswitch.ovs_neutron_plugin.'
                      'OVSNeutronPluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron')],
            'services': ['neutron-plugin-openvswitch-agent'],
            'packages': ['neutron-plugin-openvswitch-agent',
                         'openvswitch-datapath-dkms'],
        },
        'nvp': {
            'config': '/etc/neutron/plugins/nicira/nvp.ini',
            'driver': 'neutron.plugins.nicira.nicira_nvp_plugin.'
                      'NeutronPlugin.NvpPluginV2',
            'services': [],
            'packages': ['neutron-plugin-nicira'],
        },
        'n1kv': {
            'config': '/etc/neutron/plugins/cisco/cisco_plugins.ini',
            'driver': 'neutron.plugins.cisco.network_plugin.PluginV2',
            'contexts': [
                context.SharedDBContext(user=config('neutron-database-user'),
                                        database=config('neutron-database'),
                                        relation_prefix='neutron')],
            'services': ['neutron-plugin-cisco'],
            'packages': [['neutron-plugin-cisco']],
        }
    }


def neutron_plugin():
    # quantum-plugin config setting can be safely overriden
    # as we only supported OVS in G/neutron
    return config('neutron-plugin') or config('quantum-plugin')


def _net_manager_enabled(manager):
    manager = config('network-manager')
    if not manager:
        return False
    return manager.lower() == manager


def network_plugin_attribute(plugin, attr):
    manager = network_manager()
    if manager == 'quantum':
        plugins = quantum_plugins()
    elif manager == 'neutron':
        plugins = neutron_plugins()
    else:
        log('Error: Network manager does not support plugins.')
        raise Exception
    try:
        _plugin = plugins[plugin]
    except KeyError:
        log('Unrecognised plugin for %s: %s' % (manager, plugin), level=ERROR)
        raise
    try:
        return _plugin[attr]
    except KeyError:
        return None


def network_manager():
    '''
    Deals with the renaming of Quantum to Neutron in H and any situations
    that require compatability (eg, deploying H with network-manager=quantum,
    upgrading from G).
    '''
    release = os_release('nova-common')
    manager = config('network-manager').lower()

    if manager not in ['quantum', 'neutron']:
        return manager

    if release in ['essex']:
        # E does not support neutron
        log('Neutron networking not supported in Essex.', level=ERROR)
        raise
    elif release in ['folsom', 'grizzly']:
        # neutron is named quantum in F and G
        return 'quantum'
    else:
        # ensure accurate naming for all releases post-H
        return 'neutron'
