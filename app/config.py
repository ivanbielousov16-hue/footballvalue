"""Application configuration.

Усі ключі API читаються з середовища (environment variables). Якщо ключів немає,
застосунок працює у демо-режимі на mock-даних. Реальні провайдери підключаються
лише коли відповідний ключ заданий.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FV_", env_file=".env", extra="ignore")

    app_name: str = "FootballValue API"
    version: str = "0.1.0"

    # SQLite за замовчуванням — не потребує окремого сервера.
    database_url: str = "sqlite:///./footballvalue.db"

    # Ключі реальних провайдерів. Порожньо => використовується mock.
    api_football_key: str = ""          # https://www.api-football.com/
    # Спосіб доступу до API-Football:
    #   "apisports" — прямий (v3.football.api-sports.io, заголовок x-apisports-key)
    #   "rapidapi"  — через RapidAPI (api-football-v1.p.rapidapi.com)
    api_football_host: str = "apisports"
    # Сезон за замовчуванням (рік початку сезону). 0 => визначати з розкладу матчу.
    api_football_season: int = 0
    the_odds_api_key: str = ""          # https://the-odds-api.com/
    football_data_key: str = ""         # https://www.football-data.org/

    # Параметри моделі.
    max_goals: int = 10                 # розмір матриці рахунків для Poisson
    home_advantage: float = 1.10        # множник домашньої переваги
    dixon_coles_rho: float = -0.13      # параметр кореляції низьких рахунків

    # Мінімальна якість даних (0..1), нижче якої матч рекомендується пропустити.
    min_data_quality: float = 0.45
    # Мінімальний EV, щоб ставка вважалася потенційно цікавою.
    min_ev: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
