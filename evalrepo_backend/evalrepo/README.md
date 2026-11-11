# EvalRepo

Sistema multi-agente para la evaluación automatizada de repositorios GitHub estudiantiles en asignaturas de programación.

**Trabajo de Integración Curricular (TIC) — Universidad Técnica Particular de Loja, 2025**

---

## Arquitectura

Cinco agentes especializados coordinados por LangGraph:

| Agente | Tecnología | Responsabilidad |
|---|---|---|
| Coordinador | LangGraph | Orquesta el grafo, consolida resultados, genera alertas |
| Extracción | PyGitHub | Commits, árbol de archivos, ramas, código fuente |
| Análisis Estructural | Python | Verifica archivos requeridos y README |
| Análisis de Versionado | Python | Commits, calidad de mensajes, ramas, distribución temporal |
| Análisis de Contenido | Claude Sonnet 4.6 | Verifica requisitos funcionales en el código |

Los informes se generan con **Jinja2/HTML** y se persisten en **Supabase**.

---

## Requisitos previos

- Python 3.11+
- Cuenta en [Anthropic Console](https://console.anthropic.com) — para la API key de Claude
- Token de GitHub con permisos `repo:read`
- Proyecto en [Supabase](https://supabase.com)

---

## Instalación

```bash
git clone https://github.com/tu-usuario/evalrepo.git
cd evalrepo

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # Rellenar con tus credenciales
```

---

## Configuración del entorno (.env)

| Variable | Dónde obtenerla | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys | Requerida para Claude Sonnet 4.6 |
| `GITHUB_TOKEN` | github.com → Settings → Developer settings → PAT | Permisos: `repo:read` |
| `SUPABASE_URL` | supabase.com → Project Settings → API | URL del proyecto |
| `SUPABASE_SERVICE_KEY` | supabase.com → Project Settings → API → service_role | **Nunca exponer al frontend** |

Variables opcionales para trazabilidad con LangSmith:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=evalrepo-utpl
```

---

## Configurar Supabase

1. Abre tu proyecto en [supabase.com](https://supabase.com)
2. Ve a **SQL Editor → New query**
3. Copia y ejecuta el contenido de `supabase/schema.sql`

Esto crea las tablas `evaluations` y `repo_results` con los índices y políticas RLS necesarios.

---

## Uso

### Modo servidor (API REST + frontend React)

```bash
uvicorn main:app --reload
```

El servidor queda disponible en `http://localhost:8000`.
Documentación interactiva de la API: `http://localhost:8000/docs`

### Modo demostración (línea de comandos)

Para la demostración ante el tribunal sin necesidad del servidor:

```bash
# URLs directas
python demo.py --urls https://github.com/estudiante01/repo https://github.com/estudiante02/repo

# Desde archivo de texto (una URL por línea)
python demo.py --urls repos.txt

# Con directorio de salida personalizado
python demo.py --urls repos.txt --output ./reportes-parcial1

# Con criterios específicos por asignatura
python demo.py --urls repos.txt --criteria config/programacion-oo.yaml
```

Los informes HTML se guardan en el directorio de salida:
- `reportes/estudiante_repo.html` — informe individual por repositorio
- `reportes/consolidado.html` — resumen del grupo

---

## Personalizar criterios de evaluación

Edita `config/default.yaml` para adaptar la evaluación a tu asignatura. **No requiere modificar código.**

```yaml
estructural:
  peso: 25
  archivos_requeridos:
    - README.md
    - src/

versionado:
  peso: 40
  commits_min: 10
  ramas:
    min_ramas: 2

temporal:
  peso: 25
  alerta_concentracion:
    dias_finales: 3
    porcentaje_umbral: 70

contenido:
  peso: 10
  requisitos_funcionales:
    - "Implementar al menos 3 clases con herencia"
    - "Usar al menos 1 patrón de diseño"
```

Los pesos deben sumar 100. Guarda el archivo con otro nombre para reutilizarlo en otros ciclos.

---

## Estructura del proyecto

```
evalrepo/
├── agents/
│   ├── coordinator.py      Orquestador + routing + alertas
│   ├── content.py          Claude Sonnet 4.6 — análisis de código
│   ├── extraction.py       PyGitHub — metadatos del repositorio
│   ├── structural.py       Verificación de archivos y README
│   └── versioning.py       Commits, ramas y análisis temporal
├── config/
│   ├── criteria_loader.py  Carga y valida el YAML de criterios
│   └── default.yaml        Criterios por defecto (editable por el docente)
├── db/
│   └── supabase_client.py  Cliente Supabase (service_role)
├── reports/
│   └── generator.py        Jinja2 — generación de informes HTML
├── supabase/
│   └── schema.sql          Schema SQL para Supabase
├── templates/
│   ├── consolidated.html.j2
│   └── individual.html.j2
├── demo.py                 Script CLI de demostración
├── graph.py                StateGraph LangGraph
├── main.py                 FastAPI — API REST
├── state.py                TypedDict EvaluationState
└── requirements.txt
```

---

## API Reference

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/evaluate` | Lanza una evaluación |
| `GET` | `/evaluate/{id}` | Estado de la evaluación (para polling) |
| `GET` | `/evaluate/{id}/results` | Resultados JSON de todos los repos |
| `GET` | `/reports/{id}` | Informe consolidado HTML |
| `GET` | `/reports/{id}/{student}/{repo}` | Informe individual HTML |
| `POST` | `/criteria/validate` | Valida un YAML de criterios |

---

## Desarrollado con

- [LangGraph](https://langchain-ai.github.io/langgraph/) — orquestación de agentes
- [Claude Sonnet 4.6](https://www.anthropic.com) — análisis de contenido
- [PyGitHub](https://pygithub.readthedocs.io/) — API de GitHub
- [FastAPI](https://fastapi.tiangolo.com/) — servidor HTTP
- [Supabase](https://supabase.com/) — base de datos y persistencia
- [Jinja2](https://jinja.palletsprojects.com/) — generación de informes HTML
