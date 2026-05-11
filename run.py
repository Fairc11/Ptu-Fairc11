#!/usr/bin/env python3
"""Ptu v1.0.0 - 抖音图文/视频下载工具"""
from __future__ import annotations
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")


def main():
    import uvicorn
    print("Ptu v1.0.0 Beta")
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
