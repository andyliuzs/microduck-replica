# 2026-11-11 豆包实时语音接入:离线验证记录

## 23:4x 用户确认:长时间连续对话稳定可用 ✅

当晚连修五个叠加问题后全链稳定,用户原话「现在我能长时间对话了」:

1. **桥读循环同步等云端握手**(架构):改 create_task + 重入护栏 + 连接失败重试 3 次。
2. **`_run` 收到消息只回显不处理**(低级笔误):tts/quack 全进虚空——补上 `_handle` 分发。
3. **padd 卡在映射确认状态**(`output_blocked:true`,设备已断开):静默拦下所有语音启停;`systemctl restart padd` 解锁。诱因待查(Xbox 手柄某组合误触向导)。
4. **静音状态机整体移除**(桥+Studio 两侧):鸭子说话期间本地抑制自然产生静音段,云端自己做 VAD;不再发 `input_audio_mute/unmute.commit`——那套快速切换正是「第一轮回答后云端不再识别(像断连)」的根因;且 unmute 事件在云端握手期丢失会造成永久全聋。
5. **`tts_end` 改优雅排空**(`finish()` 哨兵):云端整段音频突发下发(~200ms 发完),立即杀 aplay 会切掉缓冲里没播完的语音;现在播完自然退出,排空期间麦克风保持抑制防自声回灌。TTS 队列上限 256KB→2MB。

诊断手段:两侧逐环 WARNING 日志(模式切换来源/会话起止/TTS 转发/桥接收/aplay 启停)、py-spy 线程栈、wlan0 TX 字节增量、ss socket 归属。真机实测:连续两轮对话不重开会话,识别/回答/工具调用/人声 TTS 全通;用户确认长时间对话稳定。

**已知遗留(不阻塞使用)**:TTS 到达时若恰有其他声音占用 ALSA 设备,aplay 报 `Device or resource busy` 该段丢失(加设备重试等待可解,未做);诊断日志仍是 WARNING 级(稳定后收回 INFO);Studio 重启后回答方式回默认 quack(页面按钮重选);padd 误触映射的诱因未查。

---

范围:代码交付 + Windows 开发机离线自测 + **真实云端电脑端闭环**(用户提供 API Key) + **鸭子真机部署与云端会话验证**(<真机名/局域网IP,见本地记忆>)。语音对话的开口说话验收(R3 实测听感、动作)仍待用户现场使用。

## 部署后白屏修复(2026-11-11 下午,用户现场报"页面一片空白")

- **根因(用户控制台日志直接定位)**:`ReferenceError: dlg is not defined at Overview (app.js:696)`。三个 web 文件里我用脚本替换"第一处匹配"时打错了组件:① `app.js` 里 `dialogue=${dlg}` 落在 `Overview`(状态 `dlg` 在 App 壳)——修法:Overview 增加 `dialogue` prop、App 壳实例化处传入;② `pad.js` 里 `dialogue=${dialogue}` 落在 `Remote`(prop 只加给了 `PadPage`)——修法:`Remote` 增加 prop、`PadPage` 渲染 `Remote` 处传入。教训:跨组件传 props 不能靠"替换第一处匹配"的补丁,必须先 grep 所有调用点。
- **白屏防护**:app.js 末尾加了 `Boundary`(preact `getDerivedStateFromError`),渲染错误直接显示在页面而不是空白。
- **本地完整验证后才放行**:本地起 `dev/fake_robotd.py` + `run.py --dev-autologin`(127.0.0.1:8010),受控浏览器逐页验证:总览(仪表带/电池/IMU/上手清单全渲染)、遥控页(语音与音乐互动/AI 对话面板/回答方式/字幕区全在,无渲染错误)、设置页(AI 卡片、「豆包·实时语音」供应商、文字试聊,无渲染错误)。`node --test` 前端 0 fail,python 定向测试 OK。设置页过时文案(「实时语音尚未接入」)已更新。
- 待部署:`deployment/voice_dialogue_webfix_20261111.sh`(推 app.js/pad.js/settings-ai.js → 重冻结清单 → 守卫 → 重启),鸭子回家连上网后一键跑。
- **19:18 已部署并真机验证**:脚本一次通过(3 文件重冻结、GUARD_PASS、四服务 active、healthz 200、桥已连),受控浏览器注入会话后逐页核对——真机总览(仪表带/电池/IMU/ToF 全渲染)与遥控页(AI 对话面板/监听按钮/回答方式/站走坐)均无渲染错误。白屏修复闭环,等待用户开口验收语音对话。
- **20:0x 用户首测反馈**:能聊但只鸭叫、无人声。20:01 加诊断日志部署后暴露真问题:桥每 2-5 秒断开重连、会话从不启动(Studio 日志全空——仓库 root logger 只放行 WARNING,标准 logging INFO 全被吞)。**根因(第三处同类错)**:`_bridge_event` 在桥的读循环里**同步 await `_start_session`**,云端 TLS 握手期间读循环停摆,鸭子侧 20ms PCM 灌满缓冲 → 桥 0.5s sendall 超时 → 判死连接;部分循环里会话起在又秒断,页面反复弹「dialogue bridge has no studio connection」。
- **20:2x 架构修复并部署**:`_start_session`/`_end_session` 改为 create_task(绝不阻塞桥读循环)、`_starting` 重入护栏、云端连接失败重试 3 次(3s 间隔)后再关对话、桥读循环每事件异常隔离(单个事件不再拖垮整条桥)、EOF 断开走既有重连;诊断日志升 WARNING 级(模式切换来源/会话起止/TTS 转发/连接失败原因,临时,稳定后收回 INFO)。测试等待竞态同步修正(10/10 绿)。
- **20:2x 真机复验**:对话关→开切换触发 `_start_session`,`dialogue: cloud session started (human mode)` 落日志;**会话期间桥 0 次断开**(修复前每 2-5 秒一次);云端 443 ESTAB 确认;关闭后状态干净。人声模式记忆在服务内存(Studio 重启后回 quack,页面按钮重选即可)。**待用户开口验收人声听感。**

## 真机部署(<真机,名字见本地记录>,2026-11-11)

- SSH(radxa@<鸭子局域网IP>,免密)staging 部署:`~/.voice-dialogue-staging-20261111`(duck-echo 5 文件、studio 12 文件),双侧 SHA-256 一致,Py3.13 编译预检通过;安装到 `/opt/microduck/software/current/`(→ releases/2026.11.4),备份在 `/home/radxa/.microduck-backups/voice-dialogue-20261111/`(原 15 文件 + MANIFEST)。
- **部署揭示冻结发布守卫**:`duck-echo.service` 有 drop-in `zzzzzz-microduck-controller-bundle.conf`,ExecStartPre 跑 root 的 `voice-guard.py`——compatibility.json `required:true` 时核对 `duck_echo.py`/`pad_mapping.py` 哈希与 `suite-version.json` 一致,不一致拒绝启动。首次重启 duck-echo 因此失败(每 3 秒重启循环)。**处理**:重算清单中全部文件的真实哈希并回写(守卫保持启用、通过),重启后 GUARD_PASS。注意:这偏离了"冻结发布只能经签名包变更"的原则,是开发机上的临时重冻结;正式发版仍应走 build_package 签名包。
- 服务状态:duck-echo / microduck-studio / robotd / padd 全 active;`/run/duck-echo/{control,audio}.sock` 在;healthz 200(suite 2026.11.4);桥连接日志「dialogue bridge client connected」。
- 部署中发现并修复两个真问题:① `ai_connections._public` 对 realtime 供应商把空音色记为缺项→ready 永远 False(音色留空本应走默认女声);已修并重部署该文件+清单。② Key 经 ssh 环境变量传递被双层转义弄成 1 字符垃圾值——改用 0600 临时文件传递,入库 36 字符后删除。
- **真机云端会话验证**:写好配置后经 control.sock 开 `listening+dialogue`,鸭子本机出现到豆包边缘(111.225.154.141:443)的 ESTAB WebSocket 会话;关回 listening/dialogue 后连接断开、状态干净。401 错误路径也曾在坏 Key 下复现(鉴权链路正常)。
- 本机之前部署探针留下的配置:ai-connections.json 现有「豆包实时语音」连接(name 豆包实时语音,provider doubao_realtime,API Key 已设,音色留空=默认女声)并设为当前;原有文字模型连接未动。

## 真实云端闭环(电脑端,2026-11-11,用户提供 API Key)

- 首连:真 Key 握手 → `session.create` → `session.created`(session.id 返回);错误 Key 握手被 401 拒绝(错误路径正常)。
- 全链路:SAPI 合成中文语音(慧慧音色,22050Hz→16k)→ `input_audio_unmute.commit` + 实时流式 `append` + `commit` → 识别完成事件返回 **"你好，小鸭子，请坐下。"** → `response.function_call_arguments.done`(items 数组)带 `duck_action {"action":"sit"}` → 按 items 回填工具结果 → AI 语音回答 **"乖乖坐好啦，有什么事都可以跟我说哦。"**(response.output_audio 3.4s pcm_s16le 24k,usage 6121 tokens,回填音频存电脑临时目录)。
- **实连发现并已修复生产代码的两个真 bug**:① 识别文字在 `text` 字段(原实现读 transcript,字幕会全空);② 工具调用在 `items` 数组(原实现读顶层三字段,call_id 全 None、无法回填,云端挂起到 TTS 空转超时)。mock 与单测同步为真实字段形状。
- **实连确认的协议行为**:unmute 后音频流不能停(静音也要持续推),否则约 30-40 秒后云端报 `AudioTTSIdleTimeoutError`(52000016/55000000);停止供流的应用层测试会话无法收到回答。duck-echo 桥在监听期间持续推流,设计天然满足。
- Key 只经环境变量传入临时脚本,未写入仓库、未出现在日志。

## 单元与集成(Windows 开发机)

| 套件 | 结果 |
| --- | --- |
| duck-echo 全量(`python -m unittest discover`,含新增 `test_dialogue_bridge.py`) | 165 通过,19 跳过(Linux-only,与改动无关) |
| studio `tests.test_realtime_voice`(新增:分类器/WS 握手与掩码帧/会话状态机/配置校验/动作护栏) | 10 通过 |
| studio `tests.test_ai_connections` + `tests.test_audio_interaction`(受 schema/状态字段影响的旧套件) | 21 通过 |
| studio `tests.test_pad`(audio 开关放行 dialogue) | 159 通过 |
| 前端 ESM 语法(`node --check` as .mjs:settings-ai/ai-ui-state/audio-interaction/app/pad) | 通过 |

离线闭环:本地 mock 服务(`tests/mock_doubao.py`)实现事件子集(session.create/append/mute/工具调用/文字+音频 delta/response.done),`tests.test_realtime_voice` 用注入的假 WS 与假桥驱动 `RealtimeVoiceService`,验证:端点与 X-Api-Key 传递、工具调用→tool 结果回填(成功与拒绝两条路)、鸭叫模式按文字配 tag 且不发 TTS、人声模式转发 TTS 并 tts_end 收尾、字幕进快照、对话开关对称。

修掉的自测发现:`pcm.queue` 内部锁与 `get/put` 混用导致的死锁(feed 路径);audio_control 的 set/dict 运算错误;mock 音频字段名与官方不一致(`data`→`delta`)。

## 明确未验证(不因本文宣称完成)

- **开口说话的现场验收**:识别你说话的听感/延迟、鸭叫配音选择、AI 指挥坐站/头部动作的实际效果、说"说人话"切换、断网 30 秒恢复、空闲 5 分钟自动挂断、R3 快速开关——都待用户现场逐项试,见下方清单。
- **打包发版**:未构建 `.software-update.tar`;本次是对开发机的 SSH 部署 + 清单重冻结,正式发版必须走 build_package 签名包。

## 真机现场验收清单(留给用户)

1. 网页遥控区「AI 对话」点「开始对话」(或开监听后按 R3),提示声后说"你好小鸭子"——看字幕与回应延迟。
2. 说"坐下"/"站起来"——AI 应调用动作工具,核对鸭子动作与姿态回读;说"点点头""叫一声"同理。
3. 说"说人话"——下一条回答应从鸭子喇叭出人声;点面板按钮切回鸭叫模式。
4. 音乐模式与对话互斥来回切;R3 关监听应同时结束对话。
5. 断鸭子 Wi-Fi 30 秒再恢复;对话放着不管约 5 分钟看是否自动挂断(省话费)。
