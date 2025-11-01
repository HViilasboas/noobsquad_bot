"""
Este módulo é apenas um ponto de entrada para os comandos do bot.
Todos os comandos foram organizados em módulos separados por responsabilidade.
"""

from .commands_music import MusicCommands
from .commands_monitor import MonitorCommands
from .commands_help import HelpCommands

__all__ = ['MusicCommands', 'MonitorCommands', 'HelpCommands']
