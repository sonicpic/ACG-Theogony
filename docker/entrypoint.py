"""单容器入口：同容器内托管 FastAPI(127.0.0.1:18000) 与 Next(WEB_PORT)。

host 网络模式下两个进程共享网络命名空间，Next 的 /api rewrite 指向
127.0.0.1:18000 即可；任一子进程退出则容器退出，交给 restart 策略拉起。
"""

import os
import subprocess
import sys
import time

WEB_PORT = os.environ.get("WEB_PORT", "58115")
API_PORT = os.environ.get("API_INTERNAL_PORT", "18000")

procs = [
    subprocess.Popen(
        ["uv", "run", "--no-dev", "uvicorn", "theogony.api.main:app", "--host", "127.0.0.1", "--port", API_PORT]
    ),
    subprocess.Popen(["npx", "next", "start", "-p", WEB_PORT], cwd="apps/web"),
]
print(f"[entrypoint] api=127.0.0.1:{API_PORT} | web=0.0.0.0:{WEB_PORT}", flush=True)

try:
    while True:
        for p in procs:
            rc = p.poll()
            if rc is not None:
                print(f"[entrypoint] 子进程 pid={p.pid} 退出 rc={rc}，容器终止待重启", flush=True)
                sys.exit(1)
        time.sleep(5)
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
