#!/usr/bin/python
# vim: syntax=python

import commands
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import yaml
import Cheetah
import common
import pickle

from os import chmod
from os import remove
from os.path import exists
from string import Template
from yaml.constructor import ConstructorError
from Cheetah.Template import Template

###############################################################################
# Supporting functions
###############################################################################


#------------------------------------------------------------------------------
# juju_log:  calls juju-log and records the message defined by the message
#            variable
#------------------------------------------------------------------------------
def juju_log(message=None):
    return (subprocess.call(['juju-log', str(message)]) == 0)


#------------------------------------------------------------------------------
# service:  Analogous to calling service on the command line to start/stop
#           and get status of a service/daemon.
#           Parameters:
#           service_name:    The name of the service to act on.
#           service_action:  The action (start, stop, status, etc.)
#           Returns: True if the command was successfully executed or False on
#                    error.
#------------------------------------------------------------------------------
def service(service_name=None, service_action=None):
    juju_log("service: %s, action: %s" % (service_name, service_action))
    if service_name is not None and service_action is not None:
        retVal = subprocess.call(
            ["service", service_name, service_action]) == 0
    else:
        retVal = False
    juju_log("service %s %s returns: %s" %
    (service_name, service_action, retVal))
    return(retVal)


#------------------------------------------------------------------------------
# unit_get:  Convenience function wrapping the juju command unit-get
#            Parameter:
#            setting_name:  The setting to get out of unit_get
#            Returns:  The requested information or None on error
#------------------------------------------------------------------------------
def unit_get(setting_name=None):
    juju_log("unit_get: %s" % setting_name)
    try:
        cmd_line = ['unit-get', '--format=json']
        if setting_name is not None:
            cmd_line.append(setting_name)
        unit_data = json.loads(subprocess.check_output(cmd_line))
    except Exception, e:
        subprocess.call(['juju-log', str(e)])
        unit_data = None
    finally:
        juju_log("unit_get %s returns: %s" % (setting_name, unit_data))
        return(unit_data)



#------------------------------------------------------------------------------
# config_get:  Returns a dictionary containing all of the config information
#              Optional parameter: scope
#              scope: limits the scope of the returned configuration to the
#                     desired config item.
#------------------------------------------------------------------------------
def config_get(scope=None):
    juju_log("config_get: %s" % scope)
    try:
        config_cmd_line = ['config-get']
        if scope is not None:
            config_cmd_line.append(scope)
        config_cmd_line.append('--format=json')
        config_data = json.loads(subprocess.check_output(config_cmd_line))
    except Exception, e:
        juju_log(str(e))
        config_data = None
    finally:
        juju_log("config_get: %s returns: %s" % (scope, config_data))
        return(config_data)


#------------------------------------------------------------------------------
# relation_get:  Returns a dictionary containing the relation information
#                Optional parameters: scope, relation_id
#                scope:        limits the scope of the returned data to the
#                              desired item.
#                unit_name:    limits the data ( and optionally the scope )
#                              to the specified unit
#                relation_id:  specify relation id for out of context usage.
#------------------------------------------------------------------------------
def relation_get(scope=None, unit_name=None, relation_id=None):
    juju_log("relation_get: scope: %s, unit_name: %s, relation_id: %s" %
    (scope, unit_name, relation_id))
    try:
        relation_cmd_line = ['relation-get', '--format=json']
        if relation_id is not None:
            relation_cmd_line.extend(('-r', relation_id))
        if scope is not None:
            relation_cmd_line.append(scope)
        else:
            relation_cmd_line.append('')
        if unit_name is not None:
            relation_cmd_line.append(unit_name)
        relation_data = json.loads(subprocess.check_output(relation_cmd_line))
    except Exception, e:
        juju_log(str(e))
        relation_data = None
    finally:
        juju_log("relation_get returns: %s" % relation_data)
        return(relation_data)



#------------------------------------------------------------------------------
# get_host_specific_config: Returns the appropriate config for the desired 
#                           hostname
#
#------------------------------------------------------------------------------
def get_host_specific_config(hostname):
     mapping=yaml.load(config_get('mapping'), Loader=yaml.loader.BaseLoader)
     print mapping
     if mapping is not None:
        for k, v in mapping.iteritems():
            if k in [hostname]:
               print("APPLY HOST SPEC CONF")
               juju_log("Config for %s to be applied" % hostname)
               return v
        print("HOST SPEC CONF NOT FOUND. APPLY GENERAL CONF")
     juju_log("Applying general config")
     default_conf = dict()
     default_conf['host_mgmt_intf']=config_get('host_mgmt_intf')
     default_conf['uplink_profile']=config_get('uplink_profile')
     default_conf['vtep_name']=config_get('vtep_port_profile')
     default_conf['vtep_port_profile']=config_get('vtep_port_profile')
     return default_conf



#------------------------------------------------------------------------------
# update_n1kv_config: Updates the /etc/n1kv/n1kv.conf file with the latest
#                     updated values in the data.yaml
#
#------------------------------------------------------------------------------
def update_n1kv_config():
   juju_log("update_n1kv_config")
   with open('data.yaml', 'r') as f:
        temp=f.read()
   n1kv_conf_data = yaml.load(temp, Loader=yaml.loader.BaseLoader)
   t2 = Template( file = 'templates/n1kv.conf.tmpl', 
        searchList = [{ 'host_mgmt_intf':n1kv_conf_data["n1kv_conf"]["host_mgmt_intf"],
                        'uplink_profile':n1kv_conf_data["n1kv_conf"]["uplink_profile"],
                        'vsm_ip':n1kv_conf_data["n1kv_conf"]["vsm_ip"],
                        'vsm_domain_id':n1kv_conf_data["n1kv_conf"]["vsm_domain_id"]   
                      }])
   juju_log(str(t2))
   outfile = file('/etc/n1kv/n1kv.conf', 'w')
   outfile.write(str(t2))
   outfile.close()
   subprocess.call(["service", "n1kv", "restart"])
  
#vemcmd reread config # re-reads the /etc/n1kv/n1kv.conf

#------------------------------------------------------------------------------
# create_vtep: Creates a vtep port on the OVS on a VXGW setup
#
#------------------------------------------------------------------------------
def create_vtep(vtep_name, vtpe_port_profile):
   print "TODO: EXEC ovsctl vtep command"
