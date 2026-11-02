"""Read padd's bounded public mapping state; never receive a session token.

Missing state on an older installation preserves defaults. A modern state
that disappears, or any present but invalid state, stops
voice until padd publishes a valid replacement. No network or robot I/O.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading

DEFAULT_BINDINGS={'r3':{'kind':'key','code':318},'select':{'kind':'key','code':314}}


class MappingRuntime:
    def __init__(self,path='/run/padd/mapping-state.json'):
        self.path=Path(path);self.key=None;self.cached=None;self.lock=threading.Lock();self.seen=False

    def read(self):
        with self.lock:
            try:
                metadata=self.path.lstat()
                self.seen=True
                key=(metadata.st_ino,metadata.st_size,metadata.st_mtime_ns,metadata.st_ctime_ns)
                if key!=self.key:
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>65536:
                        raise ValueError('invalid mapping state file')
                    fd=os.open(self.path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
                    with os.fdopen(fd,'rb') as source:raw=source.read(65537)
                    if len(raw)>65536:raise ValueError('oversized mapping state')
                    value=json.loads(raw)
                    if (not isinstance(value,dict) or value.get('version')!=1
                        or type(value.get('pid')) is not int or value['pid']<=0
                        or type(value.get('output_blocked')) is not bool):
                        raise ValueError('invalid mapping state')
                    device=value.get('device');profile=value.get('profile')
                    node=None if device is None else device.get('node')
                    if device is not None and (not isinstance(device,dict) or not isinstance(device.get('id'),str)
                        or not isinstance(node,str) or not re.fullmatch(r'/dev/input/event[0-9]+',node)):
                        raise ValueError('invalid mapping device')
                    bindings=DEFAULT_BINDINGS if profile is None else profile['bindings']
                    if not isinstance(bindings,dict) or len(bindings)>32:raise ValueError('invalid bindings')
                    selected={role:bindings[role] for role in ('r3','select') if role in bindings}
                    for binding in selected.values():
                        if (not isinstance(binding,dict) or type(binding.get('code')) is not int
                            or not 0<=binding['code']<=65535 or binding.get('kind') not in ('key','axis_button')
                            or (binding['kind']=='axis_button' and binding.get('value') not in (-1,1))):
                            raise ValueError('invalid voice binding')
                    self.cached={'node':node,'device_id':device.get('id') if device else None,
                                 'blocked':value['output_blocked'],'bindings':selected,'pid':value['pid'],'legacy':False,
                                 'profile_key':hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()}
                    self.key=key
                # The state only changes on profile/device/gate transitions. A
                # stopped daemon's last unblocked file must not authorize voice.
                if os.name=='posix':
                    try:os.kill(self.cached['pid'],0)
                    except PermissionError:
                        # padd and duck-echo use different UIDs. EPERM proves
                        # existence; the robot group grants file read, not kill.
                        pass
                return copy.deepcopy(self.cached)
            except FileNotFoundError:
                self.key=None
                if self.seen:return {'node':None,'blocked':True,'bindings':{},'legacy':False}
                return {'node':None,'device_id':None,'blocked':False,'bindings':copy.deepcopy(DEFAULT_BINDINGS),'legacy':True}
            except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):
                self.key=None
                return {'node':None,'blocked':True,'bindings':{},'legacy':False}

    def blocked(self):return self.read()['blocked']


PAD_MAPPING=MappingRuntime()


def binding_event(binding,kind,code,value):
    if not binding or binding['code']!=code:return None
    if binding['kind']=='key' and kind==1 and value in (0,1):return bool(value)
    if binding['kind']=='axis_button' and kind==3:return value==binding['value']
    return None
