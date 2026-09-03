"""Assemble a runnable agent from settings."""

import json
import logging
import os
import urllib.request
from pathlib import Path

from .config import Settings
from .core import JarvisAgent
from .logger import setup_logging, get_logger
from .memory.store import MemoryStore
from .providers.cloud import CloudProvider
from .providers.local_vulkan import LocalVulkanProvider
from .reminders import ReminderService
from .tools import apps, audio, clipboard, files, processes, screenshot, system, network, web
from .tools.registry import ToolRegistry

logger = get_logger("runtime")


def _cloud_generate(prompt: str) -> str:
    """Generate response using cloud provider."""
    url = os.environ.get("JARVIS_CLOUD_URL")
    if not url:
        raise RuntimeError(
            "Cloud provider not configured: set JARVIS_CLOUD_URL "
            "(or run with JARVIS_LOCAL=1 for local inference)"
        )
    
    try:
        logger.debug(f"Sending prompt to {url}")
        req = urllib.request.Request(
            url,
            data=json.dumps({"prompt": prompt}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("text", "")
    except urllib.error.URLError as e:
        logger.error(f"Cloud provider network error: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Cloud provider returned invalid JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected cloud provider error: {e}", exc_info=True)
        raise


def build_agent(settings: Settings | None = None) -> JarvisAgent:
    """
    Build and configure agent with all tools and providers.
    
    Args:
        settings: Agent settings (loaded from env if not provided)
    
    Returns:
        Configured JarvisAgent instance
    
    Raises:
        RuntimeError: If agent initialization fails
    """
    # Initialize settings
    settings = settings or Settings.from_env()
    logger.info(f"Building agent with settings: use_local={settings.use_local}")
    
    # Initialize provider
    try:
        if settings.use_local:
            logger.info("Using local Vulkan provider")
            provider = LocalVulkanProvider(
                settings.llama_cli,
                settings.model,
                ctx=settings.ctx,
                threads=settings.threads,
            )
        else:
            logger.info("Using cloud provider with retry logic")
            provider = CloudProvider(_cloud_generate)
    except Exception as e:
        logger.critical(f"Failed to initialize provider: {e}", exc_info=True)
        raise RuntimeError(f"Provider initialization failed: {e}")
    
    # Initialize memory and reminders
    try:
        memory_path = settings.memory_path
        reminder_path = str(Path(memory_path).with_name("jarvis_reminders.json"))
        
        reminders = ReminderService(reminder_path)
        logger.debug(f"Initialized reminders service: {reminder_path}")
    except Exception as e:
        logger.error(f"Failed to initialize reminders: {e}", exc_info=True)
        reminders = None
    
    # Register tools
    tools = ToolRegistry()
    
    try:
        # System tools
        tools.register("status", system.status)
        logger.debug("Registered tool: status")
        
        # File tools
        tools.register("search", files.search)
        tools.register("delete", files.delete, confirm=True)
        logger.debug("Registered tools: search, delete")
        
        # Application tools
        tools.register("launch", apps.launch, confirm=True)
        logger.debug("Registered tool: launch")
        
        # Audio tools
        tools.register("volume", audio.get_volume)
        tools.register("set_volume", audio.set_volume)
        logger.debug("Registered tools: volume, set_volume")
        
        # Screenshot tool
        tools.register("screenshot", screenshot.capture)
        logger.debug("Registered tool: screenshot")
        
        # Process tools
        tools.register(
            "ps",
            lambda *f: "\n".join(
                f"{p['pid']:>7}  {p['name']}" for p in processes.list_processes(*f)
            ) or "Не найдено"
        )
        tools.register("kill", processes.kill_process, confirm=True)
        logger.debug("Registered tools: ps, kill")
        
        # Clipboard tools
        tools.register("clip_get", lambda: clipboard.get())
        tools.register("clip_set", clipboard.set)
        logger.debug("Registered tools: clip_get, clip_set")
        
        # Network tools
        tools.register("internet", lambda: str(network.check_internet()))
        tools.register("ping", network.ping)
        tools.register("dns", network.get_dns)
        logger.debug("Registered tools: internet, ping, dns")
        
        # Web tools
        tools.register("open", web.open_url)
        tools.register("websearch", web.search_web)
        tools.register("title", web.get_webpage_title)
        logger.debug("Registered tools: open, websearch, title")
        
        # Reminder tools
        if reminders:
            tools.register("remind", reminders.add)
            tools.register("reminders", reminders.list_pending)
            logger.debug("Registered tools: remind, reminders")
        
        logger.info(f"Registered {len(tools.names())} tools")
    
    except Exception as e:
        logger.critical(f"Failed to register tools: {e}", exc_info=True)
        raise RuntimeError(f"Tool registration failed: {e}")
    
    # Create and return agent
    try:
        agent = JarvisAgent(
            provider,
            tools=tools,
            memory=MemoryStore(settings.memory_path),
            reminders=reminders
        )
        logger.info("Agent initialized successfully")
        return agent
    except Exception as e:
        logger.critical(f"Failed to create agent: {e}", exc_info=True)
        raise RuntimeError(f"Agent creation failed: {e}")
