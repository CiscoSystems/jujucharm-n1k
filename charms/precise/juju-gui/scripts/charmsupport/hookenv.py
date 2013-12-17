"Interactions with the Juju environment"
# source: 27:lp:charmsupport
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  Matthew Wedgwood <matthew.wedgwood@canonical.com>

import os
import json
import yaml
import subprocess

CRITICAL = "CRITICAL"
ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"
DEBUG = "DEBUG"
def log(message, level=DEBUG):
    "Write a message to the juju log"
    subprocess.call( [ 'juju-log', '-l', level, message ] )

class Serializable(object):
    "Wrapper, an object that can be serialized to yaml or json"
    def __init__(self, obj):
        # wrap the object
        super(Serializable, self).__init__()
        self._wrapped_obj = obj

    def __getattr__(self, attr):
        # see if this object has attr
        if attr in self.__dict__:
            return getattr(self, attr)
        # proxy to the wrapped object
        return self[attr]

    def __getitem__(self, key):
        return self._wrapped_obj[key]

    def json(self):
        "Serialize the object to json"
        return json.dumps(self._wrapped_obj)

    def yaml(self):
        "Serialize the object to yaml"
        return yaml.dump(self._wrapped_obj)

def execution_environment():
    """A convenient bundling of the current execution context"""
    context = {}
    context['conf'] = config()
    context['unit'] = local_unit()
    context['rel'] = relations_of_type()
    context['env'] = os.environ
    return context

def in_relation_hook():
    "Determine whether we're running in a relation hook"
    return os.environ.has_key('JUJU_RELATION')

def relation_type():
    "The scope for the current relation hook"
    return os.environ['JUJU_RELATION']
def relation_id():
    "The relation ID for the current relation hook"
    return os.environ['JUJU_RELATION_ID']
def local_unit():
    "Local unit ID"
    return os.environ['JUJU_UNIT_NAME']
def remote_unit():
    "The remote unit for the current relation hook"
    return os.environ['JUJU_REMOTE_UNIT']

def config(scope=None):
    "Juju charm configuration"
    config_cmd_line = ['config-get']
    if scope is not None:
        config_cmd_line.append(scope)
    config_cmd_line.append('--format=json')
    try:
        config_data = json.loads(subprocess.check_output(config_cmd_line))
    except (ValueError, OSError, subprocess.CalledProcessError) as err:
        log(str(err), level=ERROR)
        raise err
    return Serializable(config_data)

def relation_ids(reltype=None):
    "A list of relation_ids"
    reltype = reltype or relation_type()
    relids = []
    relid_cmd_line = ['relation-ids', '--format=json', reltype]
    relids.extend(json.loads(subprocess.check_output(relid_cmd_line)))
    return relids

def related_units(relid=None):
    "A list of related units"
    relid = relid or relation_id()
    units_cmd_line = ['relation-list', '--format=json', '-r', relid]
    units = json.loads(subprocess.check_output(units_cmd_line))
    return units

def relation_for_unit(unit=None):
    "Get the json represenation of a unit's relation"
    unit = unit or remote_unit()
    relation_cmd_line = ['relation-get', '--format=json', '-', unit]
    try:
        relation = json.loads(subprocess.check_output(relation_cmd_line))
    except (ValueError, OSError, subprocess.CalledProcessError), err:
        log(str(err), level=ERROR)
        raise err
    for key in relation:
        if key.endswith('-list'):
            relation[key] = relation[key].split()
    relation['__unit__'] = unit
    return Serializable(relation)

def relations_for_id(relid=None):
    "Get relations of a specific relation ID"
    relation_data = []
    relid = relid or relation_ids()
    for unit in related_units(relid):
        unit_data = relation_for_unit(unit)
        unit_data['__relid__'] = relid
        relation_data.append(unit_data)
    return relation_data

def relations_of_type(reltype=None):
    "Get relations of a specific type"
    relation_data = []
    if in_relation_hook():
        reltype = reltype or relation_type()
        for relid in relation_ids(reltype):
            for relation in relations_for_id(relid):
                relation['__relid__'] = relid
                relation_data.append(relation)
    return relation_data

class UnregisteredHookError(Exception): pass

class Hooks(object):
    def __init__(self):
        super(Hooks, self).__init__()
        self._hooks = {}
    def register(self, name, function):
        self._hooks[name] = function
    def execute(self, args):
        hook_name = os.path.basename(args[0])
        if hook_name in self._hooks:
            self._hooks[hook_name]()
        else:
            raise UnregisteredHookError(hook_name)
