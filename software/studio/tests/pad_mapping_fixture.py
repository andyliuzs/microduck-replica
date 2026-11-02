"""Only the native input/controller boundary is simulated; real Studio/WS/auth."""
import copy
import json
import os
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'deps'),str(ROOT)]
from studio import pad
from tests.test_pad_mapping import Native


class InputFixture(Native):
    def call(self, request):
        raw=json.loads(Path(os.environ['PAD_MAPPING_INPUT']).read_text(encoding='utf-8'))
        self.status['raw']=raw
        if raw.get('disconnect'): self.status['device']=None
        elif self.status['device'] is None:
            from tests.test_pad_mapping import device
            self.status['device']=device()
        result=super().call(request)
        if request['op']=='begin':self.preview_bindings=copy.deepcopy((self.status.get('profile') or {}).get('bindings',{}))
        if request['op']=='preview': self.preview_bindings=request['bindings']
        bindings=(getattr(self,'preview_bindings',{}) if (self.status.get('session') or {}).get('phase')=='learning'
                  else (self.status.get('profile') or {}).get('bindings',{}))
        mapped={'buttons':{},'axes':{}}
        for role,b in bindings.items():
            if b['kind']=='key': value=raw['buttons'].get(str(b['code']),False)
            elif b['kind']=='axis_button': value=raw['axes'].get(str(b['code']),0)==b['value']
            else:
                value=raw['axes'].get(str(b['code']),b['center'])
                if role in ('lt','rt'):
                    value=(value-b['min'])/(b['max']-b['min']); value=1-value if b['invert'] else value
                else:
                    delta=value-b['center']; span=(b['max']-b['center']) if delta>=0 else (b['center']-b['min'])
                    value=delta/max(1,span); value=-value if b['invert'] else value
                if abs(value)<b['deadzone']: value=0
            mapped['axes' if role in pad_mapping_axes else 'buttons'][role]=value
        if (self.status.get('session') or {}).get('phase')=='learning': self.status['preview']=mapped
        elif self.status.get('profile'): self.status['mapped']=mapped
        if (self.status.get('session') or {}).get('phase')=='waiting_neutral' and not any(raw['buttons'].values()) and all(abs(v)<=1 for k,v in raw['axes'].items()):
            self.status.update(output_blocked=False,session=None)
        result['status']=copy.deepcopy(self.status)
        return result


pad_mapping_axes=('lx','ly','rx','ry','lt','rt')
original=pad.default_pad
native=InputFixture()
def create(*args,**kwargs):
    result=original(*args,**kwargs)
    from studio.pad_mapping import PadMapping
    result.mapping=PadMapping(native,guard=result._mapping_guard)
    return result
pad.default_pad=create
sys.argv[0]=str(ROOT/'run.py')
runpy.run_path(str(ROOT/'tests/audio_fixture_launcher.py'),run_name='__main__')
