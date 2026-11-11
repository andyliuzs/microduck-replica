#!/usr/bin/env bash
# 2026-11-11 晚:部署网页白屏修复(app.js / pad.js / settings-ai.js)
# 用法:  SUDO_PASS='鸭子密码' bash deployment/voice_dialogue_webfix_20261111.sh
#        (在本目录运行;需要 SSH 免密到鸭子;sudo 密码从环境变量读,不进脚本/仓库)
# 鸭子地址不对就改 DUCK=。部署完用浏览器开 http://<鸭子IP>:8000 验证总览/遥控/设置三页。
set -e
DUCK=radxa@<鸭子局域网IP>
STAGE=.voice-dialogue-staging-20261111
WEB=software/studio/web
[ -n "$SUDO_PASS" ] || { echo "先 export SUDO_PASS='鸭子的 sudo 密码'"; exit 1; }

echo "== 1/4 推送三个修复文件到鸭子 staging"
scp -q "$WEB/app.js" "$WEB/pad.js" "$WEB/settings-ai.js" "$DUCK:$STAGE/studio/web/"

echo "== 2/4 安装 + 重冻结清单 + 守卫检查 + 重启"
{ printf '%s\n' "$SUDO_PASS"; cat << 'EOF'
set -e
STAGE=/home/radxa/.voice-dialogue-staging-20261111
CUR=/opt/microduck/software/current
for f in app.js pad.js settings-ai.js; do
  install -o root -g root -m 644 "$STAGE/studio/web/$f" "$CUR/studio/web/$f"
done
python3 - << 'PYEOF'
import hashlib, json, pathlib
root = pathlib.Path('/opt/microduck/software/current')
m = json.loads((root / 'suite-version.json').read_text())
for name in ('studio/web/app.js', 'studio/web/pad.js', 'studio/web/settings-ai.js'):
    m['files'][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    print('rehashed', name)
(root / 'suite-version.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n')
PYEOF
python3 -I /usr/local/lib/microduck-controller-update/voice-guard.py && echo GUARD_PASS || { echo GUARD_FAIL; exit 1; }
systemctl restart microduck-studio
sleep 3
systemctl is-active microduck-studio duck-echo robotd padd
curl -s -o /dev/null -w 'healthz %{http_code}\n' http://127.0.0.1:8000/healthz
exit 0
EOF
} | ssh "$DUCK" "sudo -S -p '' bash -s"

echo "== 3/4 完成。4/4 浏览器验证(手动):"
echo "   打开 http://<鸭子IP>:8000 (必要时强刷) 检查: 总览正常 / 遥控页有「AI 对话」面板 / 设置页提供商有「豆包·实时语音」"
