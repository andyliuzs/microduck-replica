# 手柄重新映射／校准

用户已确认模拟器式按键学习方案并要求完整实现：点击网页目标键，再按实体手柄键；双摇杆／扳机校准，测试并保存，重连加载。与此前 AI SSH 指引一起保留在本地软件分支，当前不发布、不部署实体主板。

## 界面与职责

手柄标题旁增加「重新映射／校准」，打开独立的学习面板。按键目标包括 south/east/west/north（A/B/X/Y 的标准位置）、LB/RB、Select/Start、四方向、L3/R3、可选 Home；支持逐项选择、重录、跳过可选项、取消、恢复默认。四个摇杆轴和 LT/RT 可选为轴源或数字扳机源；摇杆按指定正方向开始，推两端并回中确认，扳机按到底再释放确认。保存前实时测试且仍禁止运动输出。必须明确图上标准键位置与用户实体印字的关系。

正常映射由同一份原始输入绑定在 padd 执行并回读给网页。默认设备沿用 gilrs 既有路径；自定义设备按内核总线类型、厂家／产品及能力组合标识保存，蓝牙／USB 模式分开。旧驱动没有新能力时明确提示升级配套 padd，不允许网页假保存或只改图标。

## 驱动边界和线协议 v1

保留 `/run/padd/pad.sock` 只读原始输入流。新增 `/run/padd/mapping.sock`，padd 所有，robot 组 0660；只接受限长的一行 JSON 并返回一行 JSON，超时／并发有界。新接口自身 `version:1`，不虚构旧版支持。默认持久化目录 `/var/lib/padd`，systemd `StateDirectory=padd`，原子保存至 `mappings.json`；新命令行参数允许隔离测试目录。

请求格式 `{op, ...}`；响应 `{ok:true,version:1,status:{...},token?:string}` 或 `{ok:false,version:1,error:string,code:string}`。

- `status`：只读。
- `begin {device_id}`：须主程序可证明已停策略且非过渡状态；主循环确认暂停输出后才返回不可预测会话 token。
- `renew {token}`：会话租期 5 秒。页面每秒续期；不会无限后台续期。
- `preview {token,bindings}`：校验并保存内存草稿，回读 preview 状态，不写磁盘／恢复运动。
- `save {token,name,bindings}`：校验完整配置并原子保存，切入等待回中的状态，清除旧按键边沿，回读成功才算保存。
- `cancel {token}`：丢弃草稿，保留旧配置，等待所有键释放／摇杆回中。
- `reset {token}`：删除当前设备自定义配置，回到默认映射，同样等待回中。

`status` 精确字段：

```
device: null | {id,name,node,unique?,bus,vendor,product,axes:[{code,name,min,max,flat,fuzz,value}],buttons:[{code,name,pressed}]}
raw: {seq:u64,buttons:{decimal_code:bool},axes:{decimal_code:i32},events:[{seq:u64,kind:u16,code:u16,value:i32}]} | null
mapped: {buttons:{role:bool},axes:{lx,ly,rx,ry,lt,rt}} | null
preview: 与 mapped 同形或 null
profile: null | {schema:1,name,bindings:{role:binding}}
session: null | {phase:"learning"|"waiting_neutral",remaining_ms:u64}
output_blocked: bool
```

会话 token 只在 begin 返回，不在普通 status 暴露。raw.events 是有界最近事件历史，每条单调 seq，客户端按 cursor 学习，不能把进入学习前已按下的键误认。设备更换／掉线和 SYN_DROPPED 使捕获失效并暂停，等待新鲜重读与回中。

绑定形状：

```
key: {kind:"key",code:u16}
axis_button: {kind:"axis_button",code:u16,value:-1|1}  # 数字十字帽
axis: {kind:"axis",code:u16,min:i32,max:i32,center:i32,invert:bool,deadzone:f64}
```

buttons 用 key 或数字十字帽；LT/RT 可用 key 或 axis；lx/ly/rx/ry 必须 axis。坐标统一向右／向下为正，扳机 0..1；padd 与 gilrs 的 Y 轴差别仅在边界转换。范围与源码能力严格校验，不能重复绑定同一个按钮／同一方向十字帽／同一轴（十字帽正负可分别用）。保存必须具备 Select、Start、lx/ly/rx/ry；其他可跳过且未设置不触发动作。数据、文件、角色、设备数量均有界。

## 安全与会话

学习只读原始数据，不发送动作。暂停时一次性清空连续速度、姿态锁存和嘴部目标，禁止技能、模式切换、长按关机、R3 语音；保留网页卸力。暂停不伪装手柄丢失，不触发丢失自动坐下。结束、超时、断线、设备替换后，须中性输入稳定后才恢复；旧边沿和长按计时不能穿越会话。

Studio 按页面连接 conn 独占持有 token；其他标签页可看状态，不能改本会话。关闭、后台、导航离开时取消或停止续租。开始前拒绝网页动作会话、运动、标定／舵机会话和更新，学习时拒绝其他网页动作入口。主板原程序仍要独立执行暂停／回中门控，不能只靠网页挡住。

## 验证

Rust 合成原始帧验证 AB 互换、摇杆换轴／反向／回中／死区、数字与模拟扳机、帽轴、保存重读、身份模式隔离、异常文件和租期／边沿门控。Python 单元验证学习、归一化合同和会话所有权，串口／输入皆用隔离 fixture。真实浏览器用同形驱动 fixture 验证从点击键学习到保存回读、重连、恢复默认和手机布局；确认无机器人运动请求。Linux 验证实际 padd 控制循环，ARM64 构建 padd。真实不同型号手柄验收单列，不冒充软件模拟已替代实物。
