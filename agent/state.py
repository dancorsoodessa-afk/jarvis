"""Single source of truth for JARVIS runtime state."""
from __future__ import annotations
from enum import Enum
from threading import Lock
from typing import Callable

class JarvisState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    EXITING = "exiting"

class StateMachine:
    """Small thread-safe state machine shared by CLI, UI, voice and IPC."""
    def __init__(self, initial: JarvisState = JarvisState.IDLE):
        self._state = initial
        self._listeners: list[Callable[[JarvisState, JarvisState], None]] = []
        self._lock = Lock()

    @property
    def state(self) -> JarvisState:
        with self._lock:
            return self._state

    def subscribe(self, listener: Callable[[JarvisState, JarvisState], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def set(self, state: JarvisState) -> JarvisState:
        with self._lock:
            old = self._state
            if old == state:
                return state
            self._state = state
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(old, state)
            except Exception:
                pass
        return state

    def idle(self): return self.set(JarvisState.IDLE)
    def listening(self): return self.set(JarvisState.LISTENING)
    def thinking(self): return self.set(JarvisState.THINKING)
    def executing(self): return self.set(JarvisState.EXECUTING)
    def speaking(self): return self.set(JarvisState.SPEAKING)
    def confirmation(self): return self.set(JarvisState.CONFIRMATION)
    def error(self): return self.set(JarvisState.ERROR)
    def exiting(self): return self.set(JarvisState.EXITING)
