from charmhelpers.core.hookenv import (
    config,
    relation_ids,
    service_name,
)

from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    ApacheSSLContext as SSLContext,
)

from charmhelpers.contrib.hahelpers.cluster import (
    determine_api_port,
    determine_haproxy_port,
)


class ImageServiceContext(OSContextGenerator):
    interfaces = ['image-service']

    def __call__(self):
        if not relation_ids('image-service'):
            return {}
        return {'glance_api_version': config('glance-api-version')}


class CephContext(OSContextGenerator):
    interfaces = ['ceph-cinder']

    def __call__(self):
        """
        Used to generate template context to be added to cinder.conf in the
        presence of a ceph relation.
        """
        # TODO: this should call is_relation_made
        if not relation_ids('ceph'):
            return {}
        service = service_name()
        return {
            'volume_driver': 'cinder.volume.driver.RBDDriver',
            # ensure_ceph_pool() creates pool based on service name.
            'rbd_pool': service,
            'rbd_user': service,
            'host': service,
        }


class HAProxyContext(OSContextGenerator):
    interfaces = ['cinder-haproxy']

    def __call__(self):
        '''
        Extends the main charmhelpers HAProxyContext with a port mapping
        specific to this charm.
        Also used to extend cinder.conf context with correct api_listening_port
        '''
        haproxy_port = determine_haproxy_port(config('api-listening-port'))
        api_port = determine_api_port(config('api-listening-port'))

        ctxt = {
            'service_ports': {'cinder_api': [haproxy_port, api_port]},
            'osapi_volume_listen_port': api_port,
        }
        return ctxt


class ApacheSSLContext(SSLContext):
    interfaces = ['https']
    external_ports = [8776]
    service_namespace = 'cinder'

    def __call__(self):
        # late import to work around circular dependency
        from cinder_utils import service_enabled
        if not service_enabled('cinder-api'):
            return {}
        return super(ApacheSSLContext, self).__call__()
