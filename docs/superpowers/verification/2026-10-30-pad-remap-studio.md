# 手柄重新映射／校准：Studio、语音和跨语言验证

本记录对应 `feat/pad-remap-studio-20261030`，设计基线 `6dc40ce`，配套 native 提交 `b5b91c4`。仅本地实现和隔离验证；未发布、推送、部署主板或访问实体鸭子。

## 实现范围

- Studio 的 `PadMapping` 只在 worker 中调用限长／限时 socket，快照只读内存；按页面连接独占 token，状态／诊断包不暴露 token。开始等待驱动 ACK 时先关闭本地动作门，ACK 丢失保守暂停，直到新鲜状态确认。五秒 native 租期独立生效。
- 用新鲜 raw cursor 学按钮、四方向帽轴、四根摇杆和模拟／数字 LT／RT；支持两端行程、中心、反向、逐轴死区和冲突拒绝。进入前按住、输入丢历史、SYN_DROPPED、设备替换都有回归。
- 编辑已保存配置时允许清除任意角色的内存草稿，用于交换 Select／Start 或摇杆轴；`skip` 仍仅限可选角色，不完整草稿仍禁止保存，原持久化配置保持不变直到完整保存。
- 页面显示 native `mapped`／`preview`，保存以驱动持久化回读为准；包含跳过、清除、重录、取消保留、恢复默认、断开重连和多页面所有权。切页和后台取消，后台停止续期，刷新不自动恢复会话。
- 网页动作、配对、录制／回放、舵机、IMU／标定、软件更新以及 REST 模型写／上传与映射互斥。模型事务锁和上传锁反向阻止开始映射；同一 WebSocket 包中的 begin／servo.open 互斥。网页卸力保留。
- duck-echo 按 native 目标节点及相同的 R3／Select 原始绑定监听，支持没有默认 318 的控制器；自定义配置省略 R3 时不回退默认。暂停取消监听／识别／待执行动作／回放，配置和设备变化重新取基线；`updates_allowed`、`motion_lease` 再次检查暂停。
- runtime 状态损坏、进程退出，或已经读过新版状态后文件消失，均保守阻止语音。跨 UID 的 `kill(pid,0)` 返回 EPERM 表示活进程，不错误地停用语音；ESRCH 仍阻止。独立安装和套件 bootstrap 的 duck-echo 服务加入 `robot` 附加组，安装／软件包清单包含共享读取模块。
- 诊断包中的 `mapping.device.unique` 复用原有 MAC 脱敏规则。

## 验证入口与证据

本机证据目录：`F:/chengshenzhilu/Robot/Microduck/artifacts/pad-remap-20261030/`。这些是本地测试产物，不提交包含浏览器 profile／临时状态的整个目录。

### Python 与接口回归

Studio 工作目录为 `software/studio`：

```powershell
py -3.13 -X utf8 -I -c "import sys;sys.path[:0]=['deps','.'];import unittest;unittest.main(module=None,argv=['x','-q','tests.test_pad_mapping','tests.test_pad_mapping_integration','tests.test_pad','tests.test_http','tests.test_models_http'])"
```

最终 **300 项全部通过**（147.878 秒），输出见 `studio-edit-swap-final.log`，名单包含输入丢历史、ACK 丢失、模型 HTTP 双向互斥，以及编辑已有配置时必需输入互换。Windows 的既有后台 audio-status `AF_UNIX` 不存在警告、临时 socket/file ResourceWarning 与 unittest 断言失败分开记录；真实 Unix socket 和语音子进程另在 Linux 验证。

额外使用 WSL Python 3.13 跑 mapping／PadOps／models HTTP 和两项 WebSocket／servo 互斥，共 **42 项全部通过**（`studio-edit-swap-linux.log`）。新 HTTP 测试等待 policies 时出现短暂 `None` 的 predicate 已修正并在 Linux 重验。

duck-echo 全量测试：Windows Python 3.13 **共 172 项，153 项通过、19 项平台／硬件测试跳过，0 失败**；WSL Ubuntu 22.04 Python 3.10 为 **172 项全部通过**（`voice-final-windows.log`、`voice-final-linux.log`）。Linux 包括真实 ALSA 替身子进程和不同 UID 的读取测试；该测试仅对子进程调用 setuid/setgid 65534，读取临时文件，不更改任何账户或真实服务。

软件 updater 全量 **共 21 项，17 项通过、4 项平台测试跳过，0 失败**。`install.py` 的 runtime 清单与 updater whitelist 已覆盖 `duck-echo/pad_mapping.py`。`install_speech.py` 没有另一个源码复制清单，它复用独立安装目录及 `install.py`。

### 真实浏览器

`tests.test_pad_mapping_e2e` 启动隔离 fake robotd、真实 Studio／认证／WebSocket 和无头 Edge；只模拟 native 原始输入边界。最终 `edit-swap-final/browser.json` 全部场景通过（19.48 秒），Runtime exceptions 为零：

- AB 交换、重复冲突不覆盖、四方向帽、模拟 LT 与数字 RT、换轴、方向校准和死区。
- native 预览、保存回读、刷新后已保存配置、无自动恢复、取消保留、断开重连、恢复默认。
- 清除已保存的必需摇杆轴时保存按钮禁用，补齐互换后再次保存，重新进入后 native 预览按交换后的真实轴更新。
- 第二连接可读但不能修改／拿到 token；切页取消、后台收到 native cancel ACK，重新可见后 UI 收敛。
- `robot.jsonl` 中没有 `robot.init/enable/do/head/mouth/move` 请求。Studio 连接时原有 `robot.pose {active:false}` 中性清理保留。
- 1440／390／320 像素没有横向溢出，主面板与页脚共六张截图，已目视检查。桌面面板避让吸顶仪表带；320 像素逐轴配置分行显示。

运行时设置新的 `PAD_MAPPING_E2E_DIR`，不要复用旧浏览器状态。发行前真实协议复核发现原测试错误地把 `robot.policies.enabled` 改为 false；它实际是配置中的模型载入开关，不是运行状态。该修改及相应错误门控已删除，原录制中的 `policies.enabled=true` 与顶层 `busStatus.policy_enabled=false` 原样保留。Windows fixture 文件替换对短暂 NTFS 共享锁进行最多 500 ms 的有界重试，仍保持原子替换。

### Python × Rust 生产 socket 合同

`tests/pad_mapping_native_contract.py` 在 Linux 启动 native 的 test-only synthetic evdev fixture，并通过实际生产 `mapping.sock` handler 使用 Studio `MappingClient`／`PadMapping`。生产程序未增加输入注入开关。最终 native 二进制来源为 `b5b91c4`：

```text
python3 software/studio/tests/pad_mapping_native_contract.py \
  --fixture /root/target-v167-autodetect-dxl2-board/debug/deps/padd-1ee51bf31d9dcfb2 \
  --dir /tmp/<新的隔离目录>
```

`cross-language-edit-swap.json` 十类结果全部通过：所有权、重复冲突、AB／全部帽方向／换轴反向死区／两种释放方向的模拟扳机／预览保存、真实 runtime 的 duck-echo 读取、磁盘重读与断开重连、取消保留、数字扳机、已保存 Select／Start 和双轴互换、恢复默认、五秒租期。对应 fixture 日志在 WSL `/tmp/pad-remap-cross-studio-edit-swap/native.log`。

native 的 Rust 单测、ARM64 构建和 QEMU version/help 由 native 分支记录；该分支报告最终 112 项 Rust 测试通过。本 Studio 测试直接运行其最终生产 socket handler，不把两份各自 mock 当作合同验证。

## 独立审查与限制

独立规格／质量审查中发现的现代状态文件丢失回退、REST 模型入口互斥、begin ACK 丢失以及跨 UID EPERM 问题均已添加红测、修复并回归。最终独立审查分别给出：**规格符合性通过，质量／安全通过；新增代码范围 Critical 0、Important 0、Minor 0**。

首轮独立复验包含 mapping／PadOps／模型 HTTP 39 项、Linux Python 3.13 WebSocket／servo 两项、Linux 语音映射 12 项（含真实不同 UID）、Rust 生产 socket × Python 九类合同、完整真实浏览器一项。原模型 select 绕过复现已返回 409 且 handler 未执行；丢失 begin 回执复现的 native 和 Studio 门均保持 blocked。独立浏览器产物在 `C:/Users/12440/AppData/Local/Temp/pad-mapping-e2e-gw4miziq`，独立合同 fixture 在 WSL `/tmp/pad-remap-independent-contract-1793364239399`。

后续必需角色草稿 `clear`／交换小修的独立增量审查同样通过，Critical／Important／Minor 均为 0。独立 22 项 unit／PadOps、真实 Rust socket 十类合同和完整浏览器（19.244 秒）全部通过；额外确认非所有者 clear、必需项 skip 和不完整 save 均拒绝，native 没有写入 save、输出仍 blocked。该增量也包含在最终 300 项全量与 Linux 42 项回归中。

独立增量产物：WSL `/tmp/pad-remap-clear-review-1793365335413`；浏览器 `C:/Users/12440/AppData/Local/Temp/pad-mapping-e2e-plcff9dj`。

### 发行前真实 wire 修复

先前通过的学习／映射测试没有证明 `policies.enabled` 的运行语义，浏览器 fixture 的错误改写曾掩盖真实停止状态仍被拒绝的问题。修复后 Studio 开始门控读取新鲜、扁平的 bus 运行字段：`phase=control`、`policy_enabled=false`、`home_recovery=false`、`torque_off_pending=false`，并确认 holding 的 HOME／扭矩或 limp 的失能证据。配置 `policies.enabled=true` 不再阻止学习；未知、旧的嵌套形状、过期和过渡状态仍拒绝，native 的独立停止证明保持不变。

除原始实机录制外，回归还使用当前 robotd 的实际 Rust `Bus::report()`／`PoliciesResult`／`RobotState` 序列化输出，原样保存在 `software/studio/tests/fixtures/robotd-stopped-wire.json`，SHA256 `aa9036954c808aa251fb3f560a302340538235abf52dc9faf66e93eb6b95e5b3`，来源见同目录说明。当前修复的 Linux 定点 46 项通过，未篡改配置开关的完整浏览器 19.926 秒通过，证据在 `artifacts/software-features-20261030/mapping-wire-browser`。独立复审核对了 Rust 生产序列化与导出测试源码，Linux integration／同包 HTTP 9 项及完整浏览器（18.926 秒）通过，有限修复 Critical／Important／Minor 均为 0；这不代表尚未实现的伴随升级 bundle 已验收。

尚需实物验收：不同厂家手柄、USB／蓝牙模式、真实 evdev 掉线与 SYN_DROPPED、手柄固件事件组合、真机中性门控及 R3 麦克风／音频。浏览器后台路径用真实页面 visibilitychange 事件处理器和 native 回执验证，但没有冒充所有手机系统的冻结／杀页行为；native 五秒租期另由真实 Rust 合同测试验证。配套 padd／Studio／duck-echo／systemd 需要一起更新，本轮不做部署。
