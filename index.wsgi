import sys
import os

# Добавляем путь к вашему приложению и виртуальному окружению
sys.path.insert(0, os.path.dirname(__file__))  # Путь к папке public_html
venv_path = os.path.join(os.path.dirname(__file__), 'venv', 'lib', 'python3.6', 'site-packages')
sys.path.insert(0, venv_path)

# Импорт приложения
from adm import app as application  # Имя основного файла с приложением, например, main.py
