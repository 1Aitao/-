# -*- coding: utf-8 -*-
"""启动入口：python run.py

默认仅本机访问 http://127.0.0.1:5000
局域网演示：设置 FMS_HOST=0.0.0.0 后重启，同一网络内通过 http://<本机IP>:5000 访问
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("FMS_HOST", "127.0.0.1")
    port = int(os.environ.get("FMS_PORT", "5000"))
    app.run(host=host, port=port, debug=False, threaded=True)
