"""Learn physical controls, while padd owns the authoritative output gate and files.

No I/O from snapshot(). Only worker calls poll/handle; conn owns a native lease.
"""
import copy
import json
import math
import socket
import threading
import time

BUTTONS = ('south','east','west','north','lb','rb','select','start','du','dd','dl','dr','l3','r3','home')
AXES = ('lx','ly','rx','ry','lt','rt')
ROLES = BUTTONS + AXES
REQUIRED = ('select','start','lx','ly','rx','ry')
LABEL = dict(zip(ROLES, ('A（下）','B（右）','X（左）','Y（上）','LB','RB','Select／返回','Start／开始',
    '十字上','十字下','十字左','十字右','L3','R3','Home','左摇杆左右','左摇杆上下','右摇杆左右','右摇杆上下','LT','RT')))


class MappingError(ValueError):
    pass


class MappingClient:
    def __init__(self, address='unix:/run/padd/mapping.sock', timeout=.8):
        self.address, self.timeout = address, timeout

    def call(self, request):
        try:
            if self.address.startswith('tcp:'):
                host, port = self.address[4:].rsplit(':',1)
                if host != '127.0.0.1': raise OSError('mapping test TCP must be loopback')
                connection = socket.create_connection((host,int(port)),self.timeout)
            else:
                connection = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                connection.settimeout(self.timeout)
                connection.connect(self.address.removeprefix('unix:'))
            with connection:
                payload=json.dumps(request,separators=(',',':'),allow_nan=False).encode()+b'\n'
                if len(payload)>16384: raise MappingError('映射配置过大')
                connection.sendall(payload)
                data=bytearray(); deadline=time.monotonic()+self.timeout
                while b'\n' not in data:
                    remaining=deadline-time.monotonic()
                    if remaining<=0: raise TimeoutError()
                    connection.settimeout(remaining)
                    chunk=connection.recv(8192)
                    if not chunk: raise OSError('mapping socket closed')
                    data.extend(chunk)
                    if len(data)>262144: raise MappingError('手柄服务回包过大')
                result=json.loads(data.split(b'\n',1)[0])
        except MappingError:
            raise
        except (OSError,ValueError,AttributeError,RecursionError):
            raise MappingError('暂时连不上手柄映射服务；请确认已安装配套新版 padd，然后重试') from None
        if not isinstance(result,dict) or result.get('version')!=1:
            raise MappingError('手柄程序尚未支持这版映射功能，请更新配套 padd')
        if result.get('ok') is not True:
            raise MappingError(str(result.get('error') or '手柄程序拒绝了本次操作')[:300])
        if not isinstance(result.get('status'),dict): raise MappingError('手柄映射状态不完整，请重试')
        return result


class PadMapping:
    def __init__(self, client=None, *, guard=None, clock=time.monotonic):
        self.client, self.guard, self.clock = client, guard or (lambda:None), clock
        self._lk, self._io = threading.RLock(), threading.Lock()
        self._state, self._at, self._next = {}, None, 0.
        self._owner, self._token, self._device = None, None, None
        self._draft, self._capture, self._error, self._message = {}, None, None, None
        self._available = False
        self._closing = False
        self._starting = False
        self._uncertain = False

    @property
    def blocked(self):
        with self._lk: return self._starting or self._uncertain or self._owner is not None or self._state.get('output_blocked') is True

    def snapshot(self, conn=None):
        with self._lk:
            stale=self._at is None or self.clock()-self._at>1.5
            status=copy.deepcopy(self._state)
            mine=self._owner is not None and conn==self._owner
            for key in ('raw',): status.pop(key,None)
            if stale:
                status.update(mapped=None,preview=None)
            return {**status,'available':self._available and not stale,'stale':stale,'mine':mine,
                    'owned':self._owner is not None,'error':self._error,'message':self._message,
                    'draft':copy.deepcopy(self._draft) if mine else {},
                    'capture':copy.deepcopy(self._capture) if mine else None,
                    'required_missing':[role for role in REQUIRED if role not in self._draft] if mine else [],
                    'output_blocked':self._starting or self._uncertain or self._owner is not None or status.get('output_blocked') is True}

    def _rpc(self, op, **values):
        if self.client is None: raise MappingError('尚未配置手柄映射服务')
        result=self.client.call({'op':op,**values})
        if result.get('ok') is not True or result.get('version')!=1 or not isinstance(result.get('status'),dict):
            raise MappingError('手柄映射服务接口不匹配，请更新配套 padd')
        return result

    def _receive(self, result):
        with self._lk:
            self._state=copy.deepcopy(result['status']); self._at=self.clock(); self._available=True
            if type(self._state.get('output_blocked')) is bool:self._uncertain=False
            if self._owner is not None:
                current=(self._state.get('device') or {}).get('id')
                if current!=self._device:
                    self._owner=self._token=None
                    self._capture=None; self._error='手柄已断开或切换，请取消后重新开始映射'
                elif self._state.get('session') is None or self._state['session'].get('phase')!='learning':
                    self._owner=self._token=None; self._capture=None
                    self._message='映射会话已结束；所有按键松开、摇杆回中后恢复控制'

    def poll(self, force=False):
        if self._closing or self.client is None or (not force and self.clock()<self._next): return
        if not self._io.acquire(blocking=False): return
        try:
            self._next=self.clock()+.2
            self._receive(self._rpc('status'))
            with self._lk: changed=self._learn()
            if changed: self._preview()
        except MappingError as error:
            with self._lk:
                self._available=False; self._error=str(error); self._capture=None
            self._next=self.clock()+3
        finally: self._io.release()

    def _owner_check(self, conn):
        if conn is None or self._owner!=conn or not self._token: raise MappingError('这个映射会话由另一个页面操作，请回到原页面')
        if (self._state.get('device') or {}).get('id')!=self._device: raise MappingError('手柄已断开或切换，请取消后重新开始')

    def _preview(self):
        with self._lk: token,bindings=self._token,copy.deepcopy(self._draft)
        self._receive(self._rpc('preview',token=token,bindings=bindings))

    def _put(self, role, binding):
        source=lambda b: (b['kind'],b['code'],b.get('value'))
        for other, previous in self._draft.items():
            # An analog axis is a single physical control, even if source kinds differ.
            same=source(previous)==source(binding) or (previous['code']==binding['code'] and
                 previous['kind'] in ('axis','axis_button') and binding['kind'] in ('axis','axis_button') and
                 'axis' in (previous['kind'],binding['kind']))
            if other!=role and same:
                raise MappingError(f'这个输入已用于 {LABEL[other]}，请先重录或清除原绑定')
        self._draft[role]=binding; self._capture=None; self._error=None
        self._message=f'{LABEL[role]} 已识别，可继续选择下一项'

    def _learn(self):
        c=self._capture
        if not c or c['state']=='error': return False
        raw=self._state.get('raw') or {}
        events=[e for e in raw.get('events',[]) if isinstance(e,dict) and type(e.get('seq')) is int and e['seq']>c['cursor']]
        if (any(e.get('kind')==0 and e.get('code')==3 for e in events)
                or (events and min(e['seq'] for e in events)>c['cursor']+1)):
            c['state']='error'; self._error='原始输入有中断，请先松开手柄，再重新学习这一项';return False
        c['cursor']=max(c['cursor'],raw.get('seq',c['cursor']))
        axes={a['code']:a for a in (self._state.get('device') or {}).get('axes',[])}
        buttons={a['code'] for a in (self._state.get('device') or {}).get('buttons',[])}
        try:
            if c['role'] in BUTTONS or c['role'] in ('lt','rt'):
                keys={e['code'] for e in events if e.get('kind')==1 and e.get('value')==1 and e.get('code') in buttons}
                hats={(e['code'],e['value']) for e in events if e.get('kind')==3 and e.get('value') in (-1,1)
                      and e.get('code') in axes and axes[e['code']]['min']==-1 and axes[e['code']]['max']==1}
                if len(keys)+len(hats)>1: raise MappingError('同时检测到多个键，请松开后重新学习这一项')
                if keys:
                    self._put(c['role'],{'kind':'key','code':next(iter(keys))}); return True
                if hats and c['role'] in BUTTONS:
                    code,value=next(iter(hats)); self._put(c['role'],{'kind':'axis_button','code':code,'value':value}); return True
            if c['role'] not in AXES: return False
            for e in events:
                a=axes.get(e.get('code'))
                if e.get('kind')!=3 or not a or a['max']<=a['min']: continue
                code=e['code']; baseline=c['baseline'].get(str(code),a['value']); span=a['max']-a['min']
                value=e.get('value')
                if type(value) is not int or not a['min']<=value<=a['max']: continue
                seen=c['sweep'].setdefault(str(code),{'min':baseline,'max':baseline})
                seen['min']=min(seen['min'],value); seen['max']=max(seen['max'],value)
                if abs(value-baseline)>=span*.25:
                    if c['code'] is not None and c['code']!=code: raise MappingError('检测到多个轴在动，请只操作目标摇杆方向，再重录')
                    if c['code'] is None:
                        c.update(code=code,invert=value<baseline,state='sweeping')
            return False
        except MappingError as error:
            self._error=str(error); c['state']='error'; return False

    def _confirm_axis(self):
        c=self._capture
        if not c or c.get('code') is None or c['state']=='error': raise MappingError('还未识别到单独的摇杆轴，请按提示重录')
        role,code=c['role'],c['code']; raw=self._state.get('raw') or {}
        a=next(a for a in self._state['device']['axes'] if a['code']==code)
        center=c['baseline'].get(str(code),a['value']); sweep=c['sweep'][str(code)]
        lo,hi=sweep['min'],sweep['max']; span=a['max']-a['min']
        current=raw.get('axes',{}).get(str(code),center)
        if hi-lo<span*.5: raise MappingError('行程还不完整，请推到尽头再回中')
        if role in ('lx','ly','rx','ry') and (center-lo<span*.2 or hi-center<span*.2):
            raise MappingError('摇杆需要两个方向都推到尽头，再松手回中')
        if abs(current-center)>max(1,(hi-lo)*.12): raise MappingError('请先松手，让摇杆回中／扳机释放，再确认')
        self._put(role,{'kind':'axis','code':code,'min':lo,'max':hi,'center':center,
                        'invert':c['invert'],'deadzone':.12 if role in ('lx','ly','rx','ry') else .04})

    def handle(self, args, conn):
        action=args.get('action','status')
        allowed={'status','begin','learn','confirm_axis','skip','clear','invert','deadzone','save','cancel','reset','heartbeat'}
        if action not in allowed: raise MappingError('不支持这个映射操作')
        with self._io:
            try:
                if action=='status': self._receive(self._rpc('status'))
                elif action=='begin':
                    if conn is None: raise MappingError('请从手柄页面开始映射')
                    with self._lk:
                        if self._owner is not None: raise MappingError('已有页面正在重新映射，请先完成或取消')
                        self._starting=True
                    self.guard(); self._receive(self._rpc('status'))
                    with self._lk:
                        dev=self._state.get('device') or {}; device_id=dev.get('id')
                        if not device_id: raise MappingError('还没有读到实体手柄，请先连接手柄')
                    # A timeout cannot prove that padd did not apply begin.
                    # Keep the web gate closed until a fresh status settles it.
                    with self._lk:self._uncertain=True
                    r=self._rpc('begin',device_id=device_id)
                    if not r.get('token') or r['status'].get('output_blocked') is not True:
                        raise MappingError('手柄程序未确认暂停输出，不能开始学习')
                    self._receive(r)
                    with self._lk:
                        self._owner,self._token,self._device=conn,r['token'],device_id
                        self._draft=copy.deepcopy((r['status'].get('profile') or {}).get('bindings',{}))
                        self._capture=self._error=None; self._message='手柄动作输出已暂停；先松开所有按键，摇杆回中'
                else:
                    with self._lk:
                        if action=='cancel' and self._owner==conn:
                            token=self._token
                        else:
                            self._owner_check(conn); token=self._token
                    if action=='heartbeat': self._receive(self._rpc('renew',token=token))
                    elif action in ('cancel','reset'):
                        self._receive(self._rpc(action,token=token))
                        with self._lk:
                            self._owner=self._token=None; self._capture=None
                            self._message='已恢复默认映射，请松开所有键并让摇杆回中' if action=='reset' else '已取消，保留原映射；松开所有键并让摇杆回中'
                    elif action=='save':
                        self.guard()
                        with self._lk:
                            missing=[LABEL[r] for r in REQUIRED if r not in self._draft]
                            if missing: raise MappingError('先完成必需项：'+'、'.join(missing))
                            if self._capture is not None: raise MappingError('请先确认当前轴或取消本项学习')
                            name=args.get('name') or self._state['device']['name']
                            if not isinstance(name,str) or not name.strip() or len(name)>60: raise MappingError('名称请填 1–60 个字')
                            draft=copy.deepcopy(self._draft)
                        self._receive(self._rpc('save',token=token,name=name.strip(),bindings=draft))
                        with self._lk:
                            if (self._state.get('profile') or {}).get('bindings')!=draft: raise MappingError('驱动保存回读不一致，请保留暂停状态并重试')
                            self._owner=self._token=None; self._capture=None; self._message='映射已保存；松开所有键、摇杆回中后恢复控制'
                    else:
                        if action=='learn':
                            # Arming is a new edge boundary, not the last poll's
                            # cached frame (a held key could arrive between them).
                            self._receive(self._rpc('status'))
                        with self._lk:
                            self._owner_check(conn)
                            role=args.get('role')
                            if action!='confirm_axis' and role not in ROLES: raise MappingError('请选择一个标准按键或摇杆轴')
                            self._error=None
                            if action=='learn':
                                raw=self._state.get('raw') or {}
                                if any(raw.get('buttons',{}).values()): raise MappingError('请先松开所有按键，再点击目标键学习')
                                self._capture={'role':role,'state':'waiting','cursor':raw.get('seq',0),
                                    'baseline':copy.deepcopy(raw.get('axes',{})),'code':None,'invert':False,'sweep':{}}
                                self._message=None
                            elif action=='confirm_axis': self._confirm_axis()
                            elif action in ('skip','clear'):
                                if action=='skip' and role in REQUIRED: raise MappingError('这个是必需控制，请完成学习')
                                self._draft.pop(role,None); self._capture=None
                            elif action in ('invert','deadzone'):
                                b=self._draft.get(role)
                                if not b or b.get('kind')!='axis': raise MappingError('请先校准这个轴')
                                if action=='invert': b['invert']=not b['invert']
                                else:
                                    v=args.get('value')
                                    if type(v) not in (int,float) or not math.isfinite(v) or not .02<=v<=.3: raise MappingError('死区范围为 2%–30%')
                                    b['deadzone']=float(v)
                        if action!='learn': self._preview()
                return self.snapshot(conn)
            except MappingError as error:
                with self._lk: self._error=str(error)
                raise
            finally:
                if action=='begin':
                    with self._lk:self._starting=False

    def leave(self, conn):
        with self._lk:
            if self._owner is None or self._owner!=conn: return
            token=self._token; self._owner=self._token=None; self._capture=None
        # Event-loop callers only mark state; blocking cancellation belongs to a worker.
        def cancel():
            try:
                with self._io: self._receive(self._rpc('cancel',token=token))
            except MappingError: pass  # Native lease expires independently; output stays gated until neutral.
        threading.Thread(target=cancel,name='pad-mapping-cancel',daemon=True).start()

    def close(self):
        with self._lk: owner=self._owner
        self.leave(owner); self._closing=True
