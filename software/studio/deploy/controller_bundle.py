"""Fixed controller companion contract and explicit root transaction.

Publisher imports declarations/pure manifest functions from frozen Git bytes.
Runtime dependencies are passed by the suite-hash-verifying helper loader.
"""
import hashlib
import json
import math
import os
import re
import stat
import uuid

PAYLOAD_SCHEMA='microduck-controller-payload/1'
SCHEMA='microduck-controller-update/1'
ROBOTD_SHA256='725b74cd93660a312970a44879abe5b75e8becf108499a1b8798961e48ca5f00'
ROBOTD_SIZE=5606976
ROBOTD_SOURCE='931ce978f2efb27c157b7a583ee402793131a0d2'
ROBOTD_BUILD='0791fcd-feetech-qinmo-control.47'
# Deliberately unavailable until the release owner freezes corrected inputs.
PADD_SHA256=None
PADD_SIZE=None
PADD_SOURCE=None
SUPPORTED_PADD_SHA256=('85fc8051df2ce496abf32bbb5eba3c94c44d875365a8f33a2f53f90facba90db',)
ROBOTD='/opt/robot/feetech-ft5-r5/robotd'
PADD='/opt/robot/feetech-ft5-r5/padd'
STATE='/var/lib/microduck-helper/controller-update'
JOURNAL=STATE+'/journal.json'
COMPAT=STATE+'/compatibility.json'
VOICE_GUARD='/usr/local/lib/microduck-controller-update/voice-guard.py'
DROPIN='zzzzzz-microduck-controller-bundle.conf'
UNITS={
 '/etc/systemd/system/padd.service.d/'+DROPIN:b'[Service]\nStateDirectory=padd\nStateDirectoryMode=0750\n',
 '/etc/systemd/system/microduck-studio.service.d/'+DROPIN:b'[Service]\nSupplementaryGroups=robot\n',
 '/etc/systemd/system/duck-echo.service.d/'+DROPIN:(
     '[Service]\nSupplementaryGroups=robot\nExecStartPre=/usr/bin/python3 -I '+VOICE_GUARD+'\n').encode(),
 '/etc/systemd/system/mediad.service.d/'+DROPIN:
     b'[Service]\nRestrictAddressFamilies=\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK\n',
}
VOICE_FILES=('duck-echo/pad_mapping.py','duck-echo/duck_echo.py')
PHASES=frozenset(('prepared','guarding','replacing','verifying','restoring','completed','restored','recovery_required'))


def sha(data):return hashlib.sha256(data).hexdigest()


def bundle_manifest(version,robotd_bytes,padd_bytes):
    if not isinstance(version,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?',version):
        raise ValueError('invalid software version')
    return {'schema':PAYLOAD_SCHEMA,'architecture':'aarch64','software_version':version,
        'components':{
            'robotd':{'sha256':sha(robotd_bytes),'size':len(robotd_bytes),'source_revision':ROBOTD_SOURCE,'build':ROBOTD_BUILD,'ipc_api':42},
            'padd':{'sha256':sha(padd_bytes),'size':len(padd_bytes),'source_revision':PADD_SOURCE,'mapping_api':1,
                    'supported_installed_sha256':list(SUPPORTED_PADD_SHA256)}},
        'units':{path:{'sha256':sha(body),'mode':0o644} for path,body in UNITS.items()},
        'voice_contract':{'padd_mapping':1}}


def validate_bundle(robotd_bytes,padd_bytes,manifest,version):
    def elf(data):return (len(data)>=64 and data[:7]==b'\x7fELF\x02\x01\x01'
        and data[16:18] in (b'\x02\x00',b'\x03\x00') and data[18:20]==b'\xb7\x00')
    if (not isinstance(PADD_SHA256,str) or not re.fullmatch('[0-9a-f]{64}',PADD_SHA256)
            or not isinstance(PADD_SOURCE,str) or not re.fullmatch('[0-9a-f]{40}',PADD_SOURCE)
            or type(PADD_SIZE) is not int or not 64<=PADD_SIZE<=32*1024*1024
            or not elf(robotd_bytes) or not elf(padd_bytes)
            or (sha(robotd_bytes),len(robotd_bytes))!=(ROBOTD_SHA256,ROBOTD_SIZE)
            or (sha(padd_bytes),len(padd_bytes))!=(PADD_SHA256,PADD_SIZE)
            or manifest!=bundle_manifest(version,robotd_bytes,padd_bytes)):
        raise ValueError('controller bundle is not the frozen reviewed component vector')


def compatible_suite(metadata,files):
    contract=(metadata.get('contracts') or {}).get('padd_mapping')
    return (type(contract) is int and contract==1 and all(name in files and
            sha(files[name])==(metadata.get('files') or {}).get(name) for name in VOICE_FILES))


# A self-contained, immutable root-owned startup gate, deliberately outside the
# software release symlink. No managed module imports and no device arguments.
VOICE_GUARD_PROGRAM=r'''"""Root-owned legacy voice compatibility startup gate."""
import hashlib,json,os,stat,sys
from pathlib import Path

def guard(root='/'):
    base=Path(root)
    def read(path,limit=4*1024*1024):
        parts=path.strip('/').split('/')
        for index in range(1,len(parts)+1):
            target=base.joinpath(*parts[:index]);info=target.lstat()
            kind=stat.S_ISREG if index==len(parts) else stat.S_ISDIR
            if not kind(info.st_mode) or (os.name=='posix' and (info.st_uid!=0 or info.st_mode&0o022)):
                raise ValueError('untrusted compatibility input')
        if info.st_size>limit:raise ValueError('oversize compatibility input')
        fd=os.open(target,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as source:return source.read(limit+1)
    try:
        marker='/var/lib/microduck-helper/controller-update/compatibility.json'
        if not os.path.lexists(base/marker.lstrip('/')):return 0
        state=json.loads(read(marker,8192))
        if state.get('schema')!='microduck-controller-compat/1' or state.get('required') is not True:return 1
        current=base/'opt/microduck/software/current';release=current.resolve()
        if not current.is_symlink() or release.parent!=(base/'opt/microduck/software/releases').resolve():return 1
        relative='/'+release.relative_to(base.resolve()).as_posix()
        suite=json.loads(read(relative+'/suite-version.json'))
        contract=(suite.get('contracts') or {}).get('padd_mapping')
        if type(contract) is not int or contract!=1:return 1
        for name in ('duck-echo/pad_mapping.py','duck-echo/duck_echo.py'):
            if hashlib.sha256(read(relative+'/'+name)).hexdigest()!=(suite.get('files') or {}).get(name):return 1
        return 0
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):return 1

if __name__=='__main__':raise SystemExit(guard() if len(sys.argv)==1 else 1)
'''.encode()
