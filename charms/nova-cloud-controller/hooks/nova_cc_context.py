
from charmhelpers.core.hookenv import (
    config, relation_ids, relation_set, log, ERROR)

from charmhelpers.fetch import apt_install, filter_installed_packages
from charmhelpers.contrib.openstack import context, neutron, utils

from charmhelpers.contrib.hahelpers.cluster import (
    determine_api_port, determine_haproxy_port)


class ApacheSSLContext(context.ApacheSSLContext):

    interfaces = ['https']
    external_ports = []
    service_namespace = 'nova'

    def __call__(self):
        # late import to work around circular dependency
        from nova_cc_utils import determine_ports
        self.external_ports = determine_ports()
        return super(ApacheSSLContext, self).__call__()


class VolumeServiceContext(context.OSContextGenerator):
    interfaces = []

    def __call__(self):
        ctxt = {}

        if relation_ids('nova-volume-service'):
            if utils.os_release('nova-common') not in ['essex', 'folsom']:
                e = ('Attempting to relate a nova-volume service to an '
                     'Nova version (%s).  Use cinder.')
                log(e, level=ERROR)

                raise context.OSContextError(e)
            install_pkg = filter_installed_packages(['nova-api-os-volume'])
            if install_pkg:
                apt_install(install_pkg)
            ctxt['volume_service'] = 'nova-volume'
        elif relation_ids('cinder-volume-service'):
            ctxt['volume_service'] = 'cinder'
            # kick all compute nodes to know they should use cinder now.
            [relation_set(relation_id=rid, volume_service='cinder')
             for rid in relation_ids('cloud-compute')]
        return ctxt


class HAProxyContext(context.HAProxyContext):
    interfaces = ['ceph']

    def __call__(self):
        '''
        Extends the main charmhelpers HAProxyContext with a port mapping
        specific to this charm.
        Also used to extend nova.conf context with correct api_listening_ports
        '''
        from nova_cc_utils import api_port
        ctxt = super(HAProxyContext, self).__call__()

        # determine which port api processes should bind to, depending
        # on existence of haproxy + apache frontends
        compute_api = determine_api_port(api_port('nova-api-os-compute'))
        ec2_api = determine_api_port(api_port('nova-api-ec2'))
        s3_api = determine_api_port(api_port('nova-objectstore'))
        nvol_api = determine_api_port(api_port('nova-api-os-volume'))
        neutron_api = determine_api_port(api_port('neutron-server'))

        # to be set in nova.conf accordingly.
        listen_ports = {
            'osapi_compute_listen_port': compute_api,
            'ec2_listen_port': ec2_api,
            's3_listen_port': s3_api,
        }

        port_mapping = {
            'nova-api-os-compute': [
                determine_haproxy_port(api_port('nova-api-os-compute')),
                compute_api,
            ],
            'nova-api-ec2': [
                determine_haproxy_port(api_port('nova-api-ec2')),
                ec2_api,
            ],
            'nova-objectstore': [
                determine_haproxy_port(api_port('nova-objectstore')),
                s3_api,
            ],
        }

        if relation_ids('nova-volume-service'):
            port_mapping.update({
                'nova-api-ec2': [
                    determine_haproxy_port(api_port('nova-api-ec2')),
                    nvol_api],
            })
            listen_ports['osapi_volume_listen_port'] = nvol_api

        if neutron.network_manager() in ['neutron', 'quantum']:
            port_mapping.update({
                'neutron-server': [
                    determine_haproxy_port(api_port('neutron-server')),
                    neutron_api]
            })
            # quantum/neutron.conf listening port, set separte from nova's.
            ctxt['neutron_bind_port'] = neutron_api

        # for haproxy.conf
        ctxt['service_ports'] = port_mapping
        # for nova.conf
        ctxt['listen_ports'] = listen_ports
        return ctxt


class NeutronCCContext(context.NeutronContext):
    interfaces = []

    @property
    def plugin(self):
        from nova_cc_utils import neutron_plugin
        return neutron_plugin()

    @property
    def network_manager(self):
        return neutron.network_manager()

    @property
    def neutron_security_groups(self):
        sec_groups = (config('neutron-security-groups') or
                      config('quantum-security-groups'))
        return sec_groups.lower() == 'yes'

    def _ensure_packages(self):
        # Only compute nodes need to ensure packages here, to install
        # required agents.
        return

    def __call__(self):
        ctxt = super(NeutronCCContext, self).__call__()
        ctxt['external_network'] = config('neutron-external-network')
        if 'nvp' in [config('quantum-plugin'), config('neutron-plugin')]:
            _config = config()
            for k, v in _config.iteritems():
                if k.startswith('nvp'):
                    ctxt[k.replace('-', '_')] = v
            if 'nvp-controllers' in _config:
                ctxt['nvp_controllers'] = \
                    ','.join(_config['nvp-controllers'].split())
                ctxt['nvp_controllers_list'] = \
                    _config['nvp-controllers'].split()
        return ctxt


class IdentityServiceContext(context.IdentityServiceContext):
    def __call__(self):
        ctxt = super(IdentityServiceContext, self).__call__()
        if not ctxt:
            return

        # the ec2 api needs to know the location of the keystone ec2
        # tokens endpoint, set in nova.conf
        ec2_tokens = 'http://%s:%s/v2.0/ec2tokens' % (ctxt['service_host'],
                                                      ctxt['service_port'])
        ctxt['keystone_ec2_url'] = ec2_tokens
        return ctxt
