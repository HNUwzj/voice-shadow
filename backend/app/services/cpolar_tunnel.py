from __future__ import annotations

import atexit
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from app.config import settings

_FORWARDING_RE = re.compile(r"Forwarding\s+(https?://[^\s\"]+)\s+->\s+http://localhost:(\d+)")
_ESTABLISHED_RE = re.compile(r"Tunnel established at\s+(https?://[^\s\"]+)")


class CpolarTunnelManager:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._proc: subprocess.Popen[str] | None = None
		self._public_base_url: str | None = None
		atexit.register(self._shutdown)

	def ensure_public_base_url(self, local_port: int, force_restart: bool = False) -> str:
		with self._lock:
			if force_restart:
				self._public_base_url = None
				if self._proc is not None and self._proc.poll() is None:
					self._proc.terminate()
				self._proc = None

			if self._public_base_url:
				return self._public_base_url

			if self._proc is not None and self._proc.poll() is not None:
				self._proc = None

			if self._proc is None:
				self._proc = self._start_cpolar(local_port)

			public_url = self._read_forwarding_url(self._proc, local_port, settings.cpolar_start_timeout_sec)
			self._public_base_url = public_url.rstrip("/")
			return self._public_base_url

	def _start_cpolar(self, local_port: int) -> subprocess.Popen[str]:
		cpolar_exe = settings.cpolar_path.strip() or "cpolar"
		if cpolar_exe != "cpolar" and not Path(cpolar_exe).exists():
			raise RuntimeError(f"未找到 cpolar 可执行文件：{cpolar_exe}")

		if settings.cpolar_kill_existing:
			self._kill_existing_cpolar()

		try:
			return subprocess.Popen(
				[cpolar_exe, "http", str(local_port), "-log", "stdout", "-log-level", "INFO"],
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				encoding="utf-8",
				errors="ignore",
			)
		except Exception as exc:  # pragma: no cover - environment dependent
			raise RuntimeError(f"启动 cpolar 失败：{exc}") from exc

	def _kill_existing_cpolar(self) -> None:
		# Avoid ERR_CPOLAR_108 by clearing stale cpolar sessions before startup.
		if os.name != "nt":
			return
		try:
			subprocess.run(
				["taskkill", "/IM", "cpolar.exe", "/F"],
				capture_output=True,
				text=True,
				check=False,
			)
		except Exception:
			pass

	def _read_forwarding_url(self, proc: subprocess.Popen[str], local_port: int, timeout_sec: int) -> str:
		if proc.stdout is None:
			raise RuntimeError("cpolar 启动失败：未获得输出流。")

		deadline = time.time() + max(3, timeout_sec)
		last_lines: list[str] = []

		while time.time() < deadline:
			if proc.poll() is not None:
				break

			line = proc.stdout.readline()
			if not line:
				time.sleep(0.1)
				continue

			text = line.strip()
			if text:
				last_lines.append(text)
				if len(last_lines) > 12:
					last_lines.pop(0)

			m = _FORWARDING_RE.search(text)
			if m:
				url = m.group(1)
				target_port = int(m.group(2))
				if target_port != local_port:
					continue

				if url.startswith("https://"):
					return url
				if not self._public_base_url:
					self._public_base_url = url
				continue

			m2 = _ESTABLISHED_RE.search(text)
			if not m2:
				continue

			url = m2.group(1)

			if url.startswith("https://"):
				return url
			if not self._public_base_url:
				self._public_base_url = url

		if self._public_base_url:
			return self._public_base_url

		details = " | ".join(last_lines[-5:]) if last_lines else "无输出"
		raise RuntimeError(f"cpolar 未在限定时间内返回公网地址：{details}")

	def _shutdown(self) -> None:
		with self._lock:
			if self._proc is None:
				return
			if self._proc.poll() is None:
				self._proc.terminate()
			self._proc = None


cpolar_tunnel_manager = CpolarTunnelManager()
