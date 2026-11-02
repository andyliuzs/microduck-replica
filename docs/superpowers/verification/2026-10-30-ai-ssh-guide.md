# AI 助手 SSH 连接指引验证

日期：2026-10-30（Asia/Tokyo）。工作区：`feat/ai-ssh-guide-20261030`，基于 `bfeb2e0`；仅实现本地软件，不发布、不安装到实体主板。

## 结果

- 新增真实 Edge 端到端测试先红：旧页面没有 `.overview .ai-ssh-entry`，按预期失败；证据在工作区之外 `artifacts/ai-ssh-guide-20261030/red/`。
- 完成实现后新增浏览器测试通过。最终证据：`artifacts/ai-ssh-guide-20261030/final/browser.json` 和 `shots/`，页面异常列表为空。
- 验证了：入口与设置子路由、定位和导航高亮；首次正常（非 dev-autologin）网页密码保存后新的 cookie/CSRF 可继续设置 SSH；不匹配的确认密码不生效；保存后密码输入清空；已有网页密码、已有 SSH、公钥登录无需重设；未知状态和服务不在运行时不显示可复制的连接；操作失败可重试；公钥登记和仅公钥登录保留；连接文字不含密码；剪贴板拒绝后可手动选择文字；PowerShell 公钥路径保留反斜杠。
- 1440、390、320 像素宽度逐一检查无横向溢出，并目视检查桌面初始设置、手机已配置状态和第 3 步连接信息／复制回退截图。
- 对假 robotd 的命令记录未出现 `robot.init/enable/do/head/mouth/move`。fixture 只模拟系统 SSH 状态／密码调用，公钥目录为专用临时目录；没有修改本机系统账号、SSH 服务和个人钥匙。

## 执行命令与范围

在 `software/studio` 下，Python 3.13，使用仓库 vendored deps：

```powershell
py -3.13 -X utf8 -I -c "import sys;sys.path[:0]=['deps','.','dev'];import unittest;unittest.main(module=None,argv=['tests','-v','tests.test_ssh_guide_e2e'])"
```

最终 1 项通过，4.900 秒；`SSH_GUIDE_E2E_DIR` 指向上述 `final` 目录。独立只读审查者也运行并通过同一浏览器测试。

```powershell
py -3.13 -X utf8 -I -c "import sys;sys.path[:0]=['deps','.','dev'];import unittest;unittest.main(module=None,argv=['tests','-v','tests.test_auth_log','tests.test_sshkeys','tests.test_helper_ssh','tests.test_http'])"
```

144 项，117.274 秒，退出码 0，2 项 Linux 权限／符号链接检查在 Windows 上跳过。输出保留旧测试中的未关闭文件／socket ResourceWarning 和 Windows 无 `socket.AF_UNIX` 的音频后台线程异常；不是零警告声明。此次未修改音频或这些既有测试，也未声称全 Studio 测试套件通过。

旧 SSH 卡片浏览器回归：

```powershell
py -3.13 -X utf8 -I -c "import sys;sys.path[:0]=['deps','.','dev'];import unittest;unittest.main(module=None,argv=['tests','-v','tests.test_commit_e2e.CommitE2E.test_01d_ssh_card_on_the_more_page'])"
node --check web/settings-access.js
node --check web/app.js
node --check tests/ssh_guide_e2e.mjs
git diff --check
```

旧浏览器用例 1 项通过，3.216 秒；原断言无需修改。JS 语法和空白检查均通过。

## 审查和交付限制

独立只读代码审查完成，未发现 Critical／Important／Minor 问题，复核了认证会话衔接、旧公钥操作、密码不进入连接说明、复制回退、未知状态、路由与布局。

已有 2026.10.30 软件包及镜像保持原发布状态；本次没有新版本号、签名软件包、GitHub 推送或实体鸭子部署。真实主板 SSH 端到端验收尚未执行。
