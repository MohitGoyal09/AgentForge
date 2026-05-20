import importlib
import importlib.util
import inspect
from pathlib import Path
from config.config import Config
from tools.base import Tool
from tools.registry import ToolRegistry
from typing import Any
import sys
from config.loader import get_config_dir

class ToolDiscoveryManager:
    def __init__(self , config : Config , registry : ToolRegistry ) :
        self.config = config
        self.registry = registry
    
   
    def _load_tool_modules(self, file_path : Path ) -> Any:
        module_name = f'discovered_tool_{file_path.stem}'
        spec = importlib.util.spec_from_file_location(module_name , file_path)

        if spec is None or spec.loader is None:
            return ImportError(f'Could not load spec from {file_path}')

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        spec.loader.exec_module(module)
        return module

    def _find_tool_classes(self, module : Any ) -> list[Tool]:
        tools : list[Tool] = []
        for name in dir(module):
            obj = getattr(module , name)
            if (
                inspect.isclass(obj) 
                and issubclass(obj , Tool) 
                and obj is not Tool 
                and obj.__module__ == module.__name__ 
            ):
             tools.append(obj)
        
        return tools



    def discover_from_directory(self, directory : Path) -> None:
        tool_dir = directory / '.agentforge' / 'tools'

        if not tool_dir.exists() or not tool_dir.is_dir():
            return
        
        for py_file in tool_dir.glob('*.py'):
            try:
                if py_file.name.startswith('__'):
                        continue
                        
                module = self._load_tool_modules(py_file)
                tool_classes = self._find_tool_classes(module)

                if not tool_classes:
                        continue 

                for tool_class in tool_classes:
                    tool = tool_class(self.config)

                    self.registry.register(tool)
            except Exception:
                 continue

    def discover_all(self) -> None:
        self.discover_from_directory(self.config.cwd)
        self.discover_from_directory(get_config_dir())

