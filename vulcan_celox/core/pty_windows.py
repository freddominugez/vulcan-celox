"""Real terminal on Windows: ConPTY via ctypes, no dependency. Imported only on Windows."""

from __future__ import annotations

import ctypes
import msvcrt
import os
import threading
from ctypes import wintypes
from typing import Mapping, Optional

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
STARTF_USESTDHANDLES = 0x00000100
WAIT_INFINITE = 0xFFFFFFFF
STILL_ACTIVE = 259
HRESULT = ctypes.c_long
HPCON = wintypes.HANDLE


class COORD(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD)]


kernel32.CreatePipe.argtypes = [ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p, wintypes.DWORD]
kernel32.CreatePseudoConsole.argtypes = [COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(HPCON)]
kernel32.CreatePseudoConsole.restype = HRESULT
kernel32.ResizePseudoConsole.argtypes = [HPCON, COORD]
kernel32.ResizePseudoConsole.restype = HRESULT
kernel32.ClosePseudoConsole.argtypes = [HPCON]
kernel32.ClosePseudoConsole.restype = None
kernel32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
kernel32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.DeleteProcThreadAttributeList.restype = None
kernel32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION)]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _check(ok, what: str) -> None:
    if not ok:
        raise OSError(ctypes.get_last_error(), f"{what} falhou")


def _size(rows: int, cols: int) -> COORD:
    return COORD(max(1, int(cols)), max(1, int(rows)))


def _env_block(env: Mapping[str, str]):
    # Windows requires the block in alphabetical order, case-insensitive
    items = sorted(env.items(), key=lambda kv: kv[0].upper())
    text = "\0".join(f"{k}={v}" for k, v in items) + "\0\0"
    return ctypes.create_unicode_buffer(text, len(text))


class WinPty:
    """Process attached to a virtual console. `read_fd` and `write_fd` are plain descriptors, in binary mode."""

    def __init__(self, command_line: str, cwd: Optional[str], env: Mapping[str, str], rows: int = 24, cols: int = 80):
        in_read, in_write = wintypes.HANDLE(), wintypes.HANDLE()
        out_read, out_write = wintypes.HANDLE(), wintypes.HANDLE()
        _check(kernel32.CreatePipe(ctypes.byref(in_read), ctypes.byref(in_write), None, 0), "CreatePipe")
        _check(kernel32.CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write), None, 0), "CreatePipe")
        self.hpc = HPCON()
        result = kernel32.CreatePseudoConsole(_size(rows, cols), in_read, out_write, 0, ctypes.byref(self.hpc))
        # the console kept its ends: these closed copies are what let the read finish when it closes
        kernel32.CloseHandle(in_read)
        kernel32.CloseHandle(out_write)
        if result != 0:
            kernel32.CloseHandle(in_write)
            kernel32.CloseHandle(out_read)
            raise OSError(result, "CreatePseudoConsole falhou: é preciso Windows 10 1809 ou mais novo")
        self.closed = False
        try:
            self._start(command_line, cwd, env)
        except OSError:
            kernel32.ClosePseudoConsole(self.hpc)
            self.closed = True
            kernel32.CloseHandle(in_write)
            kernel32.CloseHandle(out_read)
            raise
        self.read_fd = msvcrt.open_osfhandle(out_read.value, os.O_RDONLY | os.O_BINARY)
        self.write_fd = msvcrt.open_osfhandle(in_write.value, os.O_WRONLY | os.O_BINARY)
        # the console does not close the output when the process ends: without this, the terminal read would wait forever
        self._lock = threading.Lock()
        self._watcher = threading.Thread(target=self._watch, name="conpty-saida", daemon=True)
        self._watcher.start()

    def _watch(self) -> None:
        kernel32.WaitForSingleObject(self.process, WAIT_INFINITE)
        self.close_console()

    def _start(self, command_line: str, cwd: Optional[str], env: Mapping[str, str]) -> None:
        size = ctypes.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attrs = ctypes.create_string_buffer(size.value)
        _check(kernel32.InitializeProcThreadAttributeList(attrs, 1, 0, ctypes.byref(size)), "InitializeProcThreadAttributeList")
        try:
            _check(kernel32.UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE, self.hpc,
                                                      ctypes.sizeof(HPCON), None, None), "UpdateProcThreadAttribute")
            info = STARTUPINFOEXW()
            info.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            # empty channels: without this, with this process's output redirected, the child inherits that output and ignores the console
            info.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            info.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)
            process = PROCESS_INFORMATION()
            line = ctypes.create_unicode_buffer(command_line)
            _check(kernel32.CreateProcessW(None, line, None, None, False, EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
                                           _env_block(env), cwd, ctypes.byref(info), ctypes.byref(process)), "CreateProcessW")
        finally:
            kernel32.DeleteProcThreadAttributeList(attrs)
        kernel32.CloseHandle(process.hThread)
        self.process = process.hProcess
        self.pid = process.dwProcessId

    def write(self, data) -> int:
        return os.write(self.write_fd, data)

    def resize(self, rows: int, cols: int) -> None:
        if not self.closed:
            kernel32.ResizePseudoConsole(self.hpc, _size(rows, cols))

    def wait(self) -> Optional[int]:
        """Waits for the process to end and returns the exit code."""
        kernel32.WaitForSingleObject(self.process, WAIT_INFINITE)
        code = wintypes.DWORD()
        return code.value if kernel32.GetExitCodeProcess(self.process, ctypes.byref(code)) else None

    def poll(self) -> Optional[int]:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(self.process, ctypes.byref(code)) or code.value == STILL_ACTIVE:
            return None
        return code.value

    def close_console(self) -> None:
        """Fecha o console: a leitura do terminal termina, e quem ainda rodava nele recebe o aviso de fechar."""
        with self._lock:
            if self.closed:
                return
            self.closed = True
        kernel32.ClosePseudoConsole(self.hpc)  # wait for the output to be read: the reader is the terminal thread

    def release(self) -> None:
        self.close_console()
        self._watcher.join(timeout=5)
        for fd in (self.read_fd, self.write_fd):
            try:
                os.close(fd)
            except OSError:
                pass
        kernel32.CloseHandle(self.process)
