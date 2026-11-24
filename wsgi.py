"""Точка входа WSGI для хостинга Alwaysdata (и любых WSGI-серверов).

Хостинг импортирует этот модуль и ищет объект `application`.
При импорте `app` автоматически выполняется инициализация БД (init_db()).
"""
from app import app as application
