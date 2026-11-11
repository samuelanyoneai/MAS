"""
db/supabase_client.py
Cliente Supabase para el backend EvalRepo.

Usa la service_role key (no la anon key) para que el backend pueda
leer y escribir sin restricciones de Row Level Security.
La service_role key NUNCA debe exponerse al frontend.
"""

from __future__ import annotations
import os
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Devuelve el cliente Supabase (singleton por proceso).
    Lee SUPABASE_URL y SUPABASE_SERVICE_KEY del entorno.
    """
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar configurados en .env\n"
            "Obtén el service_role key en: Supabase → Project Settings → API → service_role"
        )

    return create_client(url, key)
