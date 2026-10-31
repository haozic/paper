#!/usr/bin/env bash
# 党内刊物 · 本地预览服务
#
# 为什么需要它：
#   浏览器在 file:// 下禁止网页用 fetch 读取本地数据文件，直接双击 index.html
#   时三个杂志都是空的（浏览器 Console 里是 TypeError: Failed to fetch）。
#   这个脚本在本机起一个只读的静态文件服务（只监听 127.0.0.1，不对外网开放），
#   再自动打开浏览器，站内一切功能与线上相同。
#
# 用法：
#   bash start-local-server.sh          # 自动选端口并打开浏览器
#   PORT=9000 bash start-local-server.sh
#
# 停止：在本窗口按 Ctrl+C。
#
# 另一条路（不想起服务也行）：
#   python3 scripts/prepare_file_mode.py
#   然后直接双击 index.html —— 浏览器改用 <script> 载入数据副本，照样能看。

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f "index.html" ]; then
    echo "找不到 index.html，请在站点根目录（与本脚本同级）运行。"
    exit 1
fi

PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
        if "$c" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 2>/dev/null; then
            PY="$c"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "没有找到 python3 / python。"
    echo "可以改用这条路（同样不需要任何服务）："
    echo "    python3 scripts/prepare_file_mode.py"
    echo "装好 Python 3 之后重跑本脚本即可。"
    exit 1
fi

# 找一个没人占用的端口（8765 起顺延）
PORT="$("$PY" -c '
import socket
for p in range(8765, 8800):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
    except OSError:
        s.close()
        continue
    s.close()
    print(p)
    break
else:
    print("")
')"

if [ -z "$PORT" ]; then
    echo "8765～8799 都被占用了，请用 PORT=其它端口 bash start-local-server.sh"
    exit 1
fi

URL="http://127.0.0.1:${PORT}/index.html"
echo "启动本地服务：${URL}"
echo "（只监听本机 127.0.0.1，外部网络访问不到；按 Ctrl+C 停止）"

"$PY" -m http.server "$PORT" --bind 127.0.0.1 &
SERVER_PID=$!

cleanup() {
    kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 等端口起来再开浏览器
ready=0
for _ in $(seq 1 60); do
    if (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
        exec 3<&- 3>&- 2>/dev/null || true
        ready=1
        break
    fi
    sleep 0.2
done

if [ "$ready" != "1" ]; then
    echo "服务启动超时，请检查上面的报错信息。"
    exit 1
fi

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 &
else
    echo "没有找到 xdg-open / open，请手动在浏览器里打开：${URL}"
fi

wait "$SERVER_PID"
