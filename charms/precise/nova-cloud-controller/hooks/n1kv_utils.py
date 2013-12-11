#!/usr/bin/python
# vim: syntax=python
#------------------------------------------------------------------------------                                                                                                     
# This file includes supporting functions to configure parameters                                                                                                                   
# in openrc and cisco_plugins.ini                                                                                                                                                   
#                                                                                                                                                                                   
#------------------------------------------------------------------------------

import os
import subprocess
import yaml
import Cheetah
from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    charm_dir,
    log,
    relation_get,
    relation_ids,
    relation_set,
    open_port,
    unit_get,
)

from string import Template
from yaml.constructor import ConstructorError



with open('data.yaml', 'w') as f:
   f.write(yaml.dump(n1kv_conf_data, default_flow_style=True) )
common.update_n1kv_config()


