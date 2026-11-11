import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

// ─── Configuración ────────────────────────────────────────────────────────────
// Cambia USE_REAL_API a true cuando el backend esté corriendo
const USE_REAL_API = true;
const API_BASE = "http://localhost:8000";

// ─── Constantes de diseño ────────────────────────────────────────────────────
const NAVY = "#1B3A5C";

// ─── Datos mock (se usan cuando USE_REAL_API = false) ────────────────────────
const MOCK = [
  {
    id:1,student:"ana.garcia",repo:"proyecto-poo",url:"https://github.com/ana.garcia/proyecto-poo",
    score:87,pattern:"Trabajo continuo",pColor:"success",onTime:true,commits:24,branches:3,quality:83,alerts:[],
    weekly:[{w:"S1",n:3},{w:"S2",n:2},{w:"S3",n:4},{w:"S4",n:1},{w:"S5",n:5},{w:"S6",n:3},{w:"S7",n:2},{w:"S8",n:4},{w:"S9",n:0},{w:"S10",n:3}],
    struct:{score:22,max:25,files:{"README.md":true,"src/":true,"docs/":false,"tests/":true}},
    versioning:{score:35,max:40},temporal:{score:22,max:25},content:{score:8,max:10,coherence:"Alta"},
  },
  {
    id:2,student:"carlos.ruiz",repo:"tarea-final",url:"https://github.com/carlos.ruiz/tarea-final",
    score:51,pattern:"Concentración al final",pColor:"warning",onTime:true,commits:7,branches:1,quality:43,
    alerts:["85% de commits en los últimos 2 días antes de la entrega","3 semanas sin actividad (S3–S5)"],
    weekly:[{w:"S1",n:0},{w:"S2",n:0},{w:"S3",n:0},{w:"S4",n:0},{w:"S5",n:0},{w:"S6",n:0},{w:"S7",n:0},{w:"S8",n:0},{w:"S9",n:5},{w:"S10",n:2}],
    struct:{score:20,max:25,files:{"README.md":true,"src/":true,"docs/":false,"tests/":false}},
    versioning:{score:18,max:40},temporal:{score:10,max:25},content:{score:3,max:10,coherence:"Baja"},
  },
  {
    id:3,student:"maria.torres",repo:"app-web",url:"https://github.com/maria.torres/app-web",
    score:73,pattern:"Actividad irregular",pColor:"warning",onTime:false,commits:18,branches:2,quality:72,
    alerts:["Entregado tarde","2 semanas sin actividad (S4–S5)"],
    weekly:[{w:"S1",n:4},{w:"S2",n:3},{w:"S3",n:2},{w:"S4",n:0},{w:"S5",n:0},{w:"S6",n:5},{w:"S7",n:3},{w:"S8",n:1},{w:"S9",n:2},{w:"S10",n:3}],
    struct:{score:23,max:25,files:{"README.md":true,"src/":true,"docs/":true,"tests/":false}},
    versioning:{score:30,max:40},temporal:{score:15,max:25},content:{score:5,max:10,coherence:"Media"},
  },
  {
    id:4,student:"pedro.santos",repo:"sistema-bd",url:"https://github.com/pedro.santos/sistema-bd",
    score:95,pattern:"Trabajo continuo",pColor:"success",onTime:true,commits:31,branches:4,quality:91,alerts:[],
    weekly:[{w:"S1",n:3},{w:"S2",n:4},{w:"S3",n:2},{w:"S4",n:3},{w:"S5",n:4},{w:"S6",n:2},{w:"S7",n:3},{w:"S8",n:4},{w:"S9",n:3},{w:"S10",n:5}],
    struct:{score:25,max:25,files:{"README.md":true,"src/":true,"docs/":true,"tests/":true}},
    versioning:{score:38,max:40},temporal:{score:24,max:25},content:{score:8,max:10,coherence:"Alta"},
  },
  {
    id:5,student:"lucia.vargas",repo:"prog-funcional",url:"https://github.com/lucia.vargas/prog-funcional",
    score:38,pattern:"Concentración al final",pColor:"danger",onTime:false,commits:4,branches:1,quality:25,
    alerts:["Entregado tarde","4 semanas sin actividad consecutivas","92% de commits en los últimos 3 días"],
    weekly:[{w:"S1",n:0},{w:"S2",n:0},{w:"S3",n:0},{w:"S4",n:0},{w:"S5",n:0},{w:"S6",n:0},{w:"S7",n:0},{w:"S8",n:1},{w:"S9",n:2},{w:"S10",n:1}],
    struct:{score:15,max:25,files:{"README.md":false,"src/":true,"docs/":false,"tests/":false}},
    versioning:{score:12,max:40},temporal:{score:6,max:25},content:{score:5,max:10,coherence:"Media"},
  },
];

// ─── Normaliza la respuesta del API al formato interno ───────────────────────
const normalizeApiResult = (r) => {
  const vr = r.versioning_result || {};
  const tr = r.temporal_result || {};
  const sr = r.structural_result || {};
  const cr = r.content_result || {};
  const score = parseFloat(r.global_score) || 0;

  const weeklyRaw = tr.weekly_counts || {};
  const weekly = Object.entries(weeklyRaw)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, n], i) => ({ w: `S${i + 1}`, n }));

  const filesFound = sr.files_found || [];
  const filesMissing = sr.files_missing || [];
  const filesMap = {};
  filesFound.forEach(f => { filesMap[f] = true; });
  filesMissing.forEach(f => { filesMap[f] = false; });

  return {
    id: r.id,
    student: r.student,
    repo: r.repo_name,
    url: r.url,
    score,
    pattern: r.pattern_label || "Sin datos",
    pColor: score >= 70 ? "success" : score >= 50 ? "warning" : "danger",
    onTime: tr.on_time ?? false,
    commits: vr.total_commits ?? 0,
    branches: vr.branch_count ?? 0,
    quality: vr.quality_pct ?? 0,
    alerts: r.alerts || [],
    weekly: weekly.length > 0 ? weekly : [],
    struct: { score: sr.score ?? 0, max: sr.max_score ?? 25, files: filesMap },
    versioning: { score: vr.score ?? 0, max: vr.max_score ?? 40 },
    temporal: { score: tr.score ?? 0, max: tr.max_score ?? 25 },
    content: { score: cr.score ?? 0, max: cr.max_score ?? 10, coherence: cr.coherence_level ?? "N/A" },
    reportUrl: null,
  };
};

// ─── Helpers de color ─────────────────────────────────────────────────────────
const scoreColor = s => s >= 80 ? "var(--text-success)" : s >= 60 ? "var(--text-warning)" : "var(--text-danger)";
const scoreBg    = s => s >= 80 ? "var(--bg-success)"   : s >= 60 ? "var(--bg-warning)"   : "var(--bg-danger)";
const scoreBdr   = s => s >= 80 ? "var(--border-success)": s >= 60 ? "var(--border-warning)": "var(--border-danger)";

function PatternBadge({ pattern, pColor }) {
  const bg  = pColor === "success" ? "var(--bg-success)"  : pColor === "danger" ? "var(--bg-danger)"  : "var(--bg-warning)";
  const col = pColor === "success" ? "var(--text-success)" : pColor === "danger" ? "var(--text-danger)" : "var(--text-warning)";
  return <span style={{ background: bg, color: col, padding: "2px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500 }}>{pattern}</span>;
}

function NavItem({ icon, label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 10, width: "100%",
      padding: "9px 14px", border: "none", borderRadius: 8,
      background: active ? "rgba(255,255,255,0.12)" : "transparent",
      color: active ? "#fff" : "rgba(255,255,255,0.55)",
      cursor: "pointer", textAlign: "left", fontSize: 13, fontWeight: active ? 500 : 400,
      borderLeft: active ? "3px solid rgba(255,255,255,0.65)" : "3px solid transparent",
    }}>
      <span>{label}</span>
    </button>
  );
}

// ─── Vista Inicio ─────────────────────────────────────────────────────────────
function InicioView({ setView }) {
  return (
    <div style={{ padding: 24, maxWidth: 580 }}>
      <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 24, marginBottom: 20 }}>
        <div style={{ fontSize: 12, color: "var(--text-accent)", fontWeight: 500, marginBottom: 6, textTransform: "uppercase", letterSpacing: 1 }}>Sistema Multi-Agente · UTPL</div>
        <h2 style={{ margin: "0 0 10px", fontSize: 17, fontWeight: 500 }}>Evaluador de Repositorios GitHub</h2>
        <p style={{ margin: 0, color: "var(--text-secondary)", lineHeight: 1.7, fontSize: 14 }}>
          Evalúa automáticamente repositorios estudiantiles según criterios pedagógicos configurables. Cuatro agentes especializados analizan estructura, versionado, actividad temporal y contenido del código.
        </p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 20 }}>
        {[
          { icon: "settings", label: "1. Configurar criterios", desc: "Define pesos y parámetros por dimensión", tab: "criterios" },
          { icon: "player-play", label: "2. Evaluar grupo", desc: "Pega las URLs y lanza el análisis", tab: "evaluacion" },
          { icon: "chart-bar", label: "3. Ver reportes", desc: "Informes individuales y consolidado", tab: "reportes" },
        ].map(s => (
          <button key={s.tab} onClick={() => setView(s.tab)} style={{
            background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12,
            padding: 16, textAlign: "left", cursor: "pointer",
          }}
            onMouseOver={e => e.currentTarget.style.borderColor = "var(--border-accent)"}
            onMouseOut={e => e.currentTarget.style.borderColor = "var(--border)"}
          >
            <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{s.desc}</div>
          </button>
        ))}
      </div>
      <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Stack tecnológico</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {["LangGraph", "Claude Sonnet 4.6", "langchain-anthropic", "PyGitHub", "YAML", "Jinja2/HTML", "FastAPI", "Supabase"].map(t => (
            <span key={t} style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12, background: "var(--bg-accent)", color: "var(--text-accent)", border: "0.5px solid var(--border-accent)" }}>{t}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Vista Criterios ──────────────────────────────────────────────────────────
function CriteriosView() {
  const [tab, setTab] = useState("versionado");
  const [w, setW] = useState({ estructural: 25, versionado: 40, temporal: 25, contenido: 10 });
  const total = Object.values(w).reduce((a, b) => a + b, 0);
  const tabs = ["estructural", "versionado", "temporal", "contenido"];
  const dimColor = { estructural: "var(--text-pro)", versionado: "var(--text-accent)", temporal: "var(--text-warning)", contenido: "var(--text-success)" };

  return (
    <div style={{ padding: 24, maxWidth: 620 }}>
      <div style={{ display: "flex", gap: 2, marginBottom: 20, background: "var(--surface-1)", padding: 4, borderRadius: 8, width: "fit-content" }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "6px 16px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 13,
            background: tab === t ? "var(--surface-2)" : "transparent",
            color: tab === t ? "var(--text-primary)" : "var(--text-secondary)",
            fontWeight: tab === t ? 500 : 400,
          }}>{t.charAt(0).toUpperCase() + t.slice(1)}</button>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 190px", gap: 16 }}>
        <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 20 }}>
          {tab === "versionado" && <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Análisis de versionado</h3>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-secondary)", cursor: "pointer" }}><input type="checkbox" defaultChecked />Habilitado</label>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Peso (%)</label>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input type="range" min={0} max={60} value={w.versionado} onChange={e => setW(p => ({ ...p, versionado: +e.target.value }))} style={{ flex: 1 }} />
                <span style={{ fontWeight: 500, color: dimColor.versionado, minWidth: 36, textAlign: "right" }}>{w.versionado}%</span>
              </div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Commits mínimos</label>
              <input type="number" defaultValue={10} style={{ width: "100%" }} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Ramas mínimas</label>
              <input type="number" defaultValue={2} style={{ width: "100%" }} />
            </div>
            <div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, marginBottom: 8, padding: "8px 10px", background: "var(--surface-1)", borderRadius: 6 }}>
                <input type="checkbox" defaultChecked /><span>Evaluar calidad de mensajes de commit</span>
              </label>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Umbral de calidad (%)</label>
              <input type="number" defaultValue={70} style={{ width: "100%" }} />
            </div>
          </>}
          {tab === "estructural" && <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Análisis estructural</h3>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-secondary)", cursor: "pointer" }}><input type="checkbox" defaultChecked />Habilitado</label>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Peso (%)</label>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input type="range" min={0} max={50} value={w.estructural} onChange={e => setW(p => ({ ...p, estructural: +e.target.value }))} style={{ flex: 1 }} />
                <span style={{ fontWeight: 500, color: dimColor.estructural, minWidth: 36, textAlign: "right" }}>{w.estructural}%</span>
              </div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>Archivos requeridos</label>
              {["README.md", "src/", "docs/", "tests/"].map(f => (
                <label key={f} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", background: "var(--surface-1)", borderRadius: 6, marginBottom: 4, cursor: "pointer", fontSize: 13 }}>
                  <input type="checkbox" defaultChecked={f !== "docs/"} />
                  <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{f}</code>
                </label>
              ))}
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>README — mínimo de caracteres</label>
              <input type="number" defaultValue={200} style={{ width: "100%" }} />
            </div>
          </>}
          {tab === "temporal" && <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Análisis temporal</h3>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-secondary)", cursor: "pointer" }}><input type="checkbox" defaultChecked />Habilitado</label>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Peso (%)</label>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input type="range" min={0} max={40} value={w.temporal} onChange={e => setW(p => ({ ...p, temporal: +e.target.value }))} style={{ flex: 1 }} />
                <span style={{ fontWeight: 500, color: dimColor.temporal, minWidth: 36, textAlign: "right" }}>{w.temporal}%</span>
              </div>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, marginBottom: 14, padding: "8px 10px", background: "var(--surface-1)", borderRadius: 6 }}>
              <input type="checkbox" defaultChecked /><span>Verificar actividad mínima semanal</span>
            </label>
            <div style={{ background: "var(--bg-warning)", border: "0.5px solid var(--border-warning)", borderRadius: 8, padding: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text-warning)", marginBottom: 10 }}>
                Alerta de concentración
              </div>
              <div style={{ marginBottom: 10 }}>
                <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Días finales a analizar</label>
                <input type="number" defaultValue={3} style={{ width: "100%" }} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Umbral para alerta (%)</label>
                <input type="number" defaultValue={70} style={{ width: "100%" }} />
              </div>
            </div>
          </>}
          {tab === "contenido" && <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 500 }}>Análisis de contenido</h3>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-secondary)", cursor: "pointer" }}><input type="checkbox" defaultChecked />Habilitado</label>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Peso (%)</label>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input type="range" min={0} max={30} value={w.contenido} onChange={e => setW(p => ({ ...p, contenido: +e.target.value }))} style={{ flex: 1 }} />
                <span style={{ fontWeight: 500, color: dimColor.contenido, minWidth: 36, textAlign: "right" }}>{w.contenido}%</span>
              </div>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Requisitos funcionales (Claude los verificará en el código)</label>
              <textarea defaultValue={"Implementar al menos 3 clases con herencia\nUsar al menos 1 patrón de diseño\nAplicar principios SOLID"} style={{
                width: "100%", height: 110, padding: "8px 10px",
                border: "0.5px solid var(--border)", borderRadius: 8,
                fontSize: 13, fontFamily: "var(--font-sans)", lineHeight: 1.6, resize: "vertical",
                boxSizing: "border-box", background: "var(--surface-0)", color: "var(--text-primary)"
              }} />
            </div>
          </>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 12 }}>Distribución de pesos</div>
            {Object.entries(w).map(([dim, peso]) => (
              <div key={dim} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                  <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{dim.charAt(0).toUpperCase() + dim.slice(1)}</span>
                  <span style={{ fontSize: 12, fontWeight: 500, color: dimColor[dim] }}>{peso}%</span>
                </div>
                <div style={{ height: 4, background: "var(--surface-0)", borderRadius: 999 }}>
                  <div style={{ height: "100%", width: `${peso}%`, background: dimColor[dim], borderRadius: 999, transition: "width 0.3s" }} />
                </div>
              </div>
            ))}
            <div style={{
              marginTop: 10, padding: 6, borderRadius: 6, textAlign: "center", fontSize: 12, fontWeight: 500,
              background: total === 100 ? "var(--bg-success)" : "var(--bg-danger)",
              color: total === 100 ? "var(--text-success)" : "var(--text-danger)",
            }}>Total: {total}% {total === 100 ? "correcto" : "≠ 100"}</div>
          </div>
          <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Período académico</div>
            <div style={{ marginBottom: 8 }}>
              <label style={{ display: "block", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Inicio</label>
              <input type="date" defaultValue="2025-01-15" style={{ width: "100%", fontSize: 12 }} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Fecha límite</label>
              <input type="date" defaultValue="2025-06-30" style={{ width: "100%", fontSize: 12 }} />
            </div>
          </div>
          <button style={{ fontSize: 13, padding: "8px 12px", width: "100%" }}>
            Guardar config
          </button>
          <button style={{ fontSize: 13, padding: "8px 12px", width: "100%" }}>
            Cargar config
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Vista Evaluación (conectada al API real) ─────────────────────────────────
function EvaluacionView({ onDone }) {
  const [urls, setUrls] = useState(
    "https://github.com/ana.garcia/proyecto-poo\nhttps://github.com/carlos.ruiz/tarea-final\nhttps://github.com/maria.torres/app-web\nhttps://github.com/pedro.santos/sistema-bd\nhttps://github.com/lucia.vargas/prog-funcional"
  );
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState([]);
  const [evaluationId, setEvaluationId] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const logRef = useRef(null);
  const pollRef = useRef(null);

  const repoList = urls.split("\n").filter(u => u.trim());

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  // Polling cuando hay una evaluación en curso
  useEffect(() => {
    if (!evaluationId || status !== "running" || !USE_REAL_API) return;

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/evaluate/${evaluationId}`);
        const data = await res.json();

        const pct = data.total_repos > 0
          ? Math.round((data.processed_repos / data.total_repos) * 100)
          : 0;
        setProgress(pct);

        // Agregar entrada al log según progreso
        if (data.processed_repos > 0) {
          setLog(prev => {
            const last = prev[prev.length - 1];
            const msg = `[Coordinador] ${data.processed_repos}/${data.total_repos} repositorios procesados`;
            if (!last || last.t !== msg) return [...prev, { t: msg, ok: true }];
            return prev;
          });
        }

        if (data.status === "done") {
          clearInterval(pollRef.current);
          setStatus("done");
          // Obtener resultados normalizados del API
          const resultsRes = await fetch(`${API_BASE}/evaluate/${evaluationId}/results`);
          const raw = await resultsRes.json();
          onDone(raw.map(normalizeApiResult), evaluationId);
        }

        if (data.status === "error") {
          clearInterval(pollRef.current);
          setStatus("idle");
          setErrorMsg(data.errors?.[0] || "Error desconocido en la evaluación.");
        }
      } catch (e) {
        clearInterval(pollRef.current);
        setStatus("idle");
        setErrorMsg(`Error de conexión: ${e.message}`);
      }
    }, 2000);

    return () => clearInterval(pollRef.current);
  }, [evaluationId, status]);

  const run = async () => {
    if (status === "running" || !repoList.length) return;
    setStatus("running");
    setProgress(0);
    setLog([]);
    setErrorMsg("");

    if (USE_REAL_API) {
      // ── Modo real: llamar al backend ──────────────────────────────────────
      try {
        setLog([{ t: "Conectando con el servidor...", ok: false }]);
        const res = await fetch(`${API_BASE}/evaluate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ repo_urls: repoList, github_token: token }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        setEvaluationId(data.evaluation_id);
        setLog([{ t: `Evaluación iniciada (ID: ${data.evaluation_id.slice(0, 8)}…)`, ok: false }]);
      } catch (e) {
        setStatus("idle");
        setErrorMsg(`Error al iniciar: ${e.message}`);
      }
    } else {
      // ── Modo mock: simulación local ───────────────────────────────────────
      const msgs = [];
      repoList.forEach(url => {
        const name = url.split("/").pop();
        msgs.push(
          { t: `[Extracción] Obteniendo metadatos: ${name}…`, ok: false },
          { t: `[Estructural] Verificando árbol de archivos…`, ok: false },
          { t: `[Versionado] Analizando historial de commits…`, ok: false },
          { t: `[Contenido] Evaluando código con Claude Sonnet 4.6…`, ok: false },
          { t: `[Coordinador] Informe generado: ${name}`, ok: true },
        );
      });
      let i = 0;
      const iv = setInterval(() => {
        if (i < msgs.length) {
          setLog(p => [...p, msgs[i]]);
          setProgress(Math.round(((i + 1) / msgs.length) * 100));
          i++;
        } else {
          clearInterval(iv);
          setStatus("done");
          onDone(MOCK.slice(0, repoList.length), null);
        }
      }, 350);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 580 }}>
      {!USE_REAL_API && (
        <div style={{ background: "var(--bg-warning)", border: "0.5px solid var(--border-warning)", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "var(--text-warning)" }}>
          Modo demo activo — usando datos de ejemplo. Cambia <code>USE_REAL_API = true</code> para conectar al backend.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
        <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Token de GitHub</div>
          <input type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="ghp_..." style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: 12 }} />
          <p style={{ margin: "6px 0 0", fontSize: 11, color: "var(--text-muted)" }}>Con permisos repo:read</p>
        </div>
        <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Configuración activa</div>
          <select style={{ width: "100%", fontSize: 13 }}>
            <option>programacion-oo-2025</option>
            <option>algoritmos-2024</option>
            <option>bases-datos-2025</option>
          </select>
          <p style={{ margin: "6px 0 0", fontSize: 11, color: "var(--text-muted)" }}>Estructural 25% · Versionado 40% · Temporal 25% · Contenido 10%</p>
        </div>
      </div>

      <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Repositorios a evaluar — una URL por línea</div>
        <textarea value={urls} onChange={e => setUrls(e.target.value)} style={{
          width: "100%", height: 130, padding: "8px 10px",
          border: "0.5px solid var(--border)", borderRadius: 8,
          fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.8,
          resize: "vertical", boxSizing: "border-box",
          background: "var(--surface-0)", color: "var(--text-primary)"
        }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10 }}>
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{repoList.length} repositorio{repoList.length !== 1 ? "s" : ""}</span>
          <button onClick={run} disabled={status === "running"} style={{
            fontSize: 13, padding: "8px 20px",
            ...(status !== "running" ? { background: "var(--fill-accent)", color: "var(--on-accent)", border: "none" } : { cursor: "not-allowed" })
          }}>
            {status === "running" ? "Evaluando…" : "Evaluar"}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div style={{ background: "var(--bg-danger)", border: "0.5px solid var(--border-danger)", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "var(--text-danger)" }}>
          {errorMsg}
        </div>
      )}

      {(status === "running" || status === "done") && (
        <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 500 }}>Progreso</span>
            <span style={{ fontSize: 13, color: "var(--text-accent)", fontWeight: 500 }}>{progress}%</span>
          </div>
          <div style={{ height: 6, background: "var(--surface-0)", borderRadius: 999, marginBottom: 14 }}>
            <div style={{ height: "100%", width: `${progress}%`, background: "var(--fill-accent)", borderRadius: 999, transition: "width 0.35s ease" }} />
          </div>
          <div ref={logRef} style={{ maxHeight: 180, overflow: "auto", background: "#0F172A", borderRadius: 8, padding: "12px 14px", fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.9 }}>
            {log.map((e, i) => (
              <div key={i} style={{ color: e.ok ? "#34D399" : "#94A3B8" }}>{e.t}</div>
            ))}
          </div>
          {status === "done" && (
            <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 8, background: "var(--bg-success)", border: "0.5px solid var(--border-success)", color: "var(--text-success)", fontSize: 13, fontWeight: 500 }}>
              Evaluación completada — {repoList.length} repositorios procesados
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Detalle de repositorio ───────────────────────────────────────────────────
function ReporteDetalle({ r, evaluationId, onBack }) {
  const reportUrl = evaluationId
    ? `${API_BASE}/reports/${evaluationId}/${r.student}/${r.repo}`
    : null;

  return (
    <div style={{ padding: 24, maxWidth: 580 }}>
      <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, marginBottom: 16, color: "var(--text-secondary)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
        Volver a reportes
      </button>

      <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 20, marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2 style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 500 }}>
              <span style={{ color: "var(--text-secondary)" }}>{r.student}</span>
              <span style={{ color: "var(--text-muted)", margin: "0 4px" }}>/</span>
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 14 }}>{r.repo}</code>
            </h2>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <PatternBadge pattern={r.pattern} pColor={r.pColor} />
              <span style={{
                padding: "2px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500,
                background: r.onTime ? "var(--bg-success)" : "var(--bg-danger)",
                color: r.onTime ? "var(--text-success)" : "var(--text-danger)",
              }}>{r.onTime ? "Entregado a tiempo" : "Entregado tarde"}</span>
            </div>
          </div>
          <div style={{ textAlign: "center", flexShrink: 0 }}>
            <div style={{ width: 76, height: 76, borderRadius: "50%", border: `4px solid ${scoreBdr(r.score)}`, background: scoreBg(r.score), display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
              <span style={{ fontSize: 22, fontWeight: 500, color: scoreColor(r.score), lineHeight: 1 }}>{r.score}</span>
              <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>/ 100</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
        {[
          { label: "Estructural", data: r.struct, icon: "folder" },
          { label: "Versionado", data: r.versioning, icon: "git-branch" },
          { label: "Temporal", data: r.temporal, icon: "clock" },
          { label: "Contenido", data: r.content, icon: "code" },
        ].map(item => (
          <div key={item.label} style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: "12px 8px", textAlign: "center" }}>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>{item.label}</div>
            <div style={{ fontSize: 19, fontWeight: 500 }}>{item.data.score}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>/ {item.data.max}</div>
            <div style={{ marginTop: 6, height: 3, background: "var(--surface-0)", borderRadius: 999 }}>
              <div style={{ height: "100%", borderRadius: 999, width: `${Math.round((item.data.score / item.data.max) * 100)}%`, background: "var(--fill-accent)" }} />
            </div>
          </div>
        ))}
      </div>

      {r.alerts.length > 0 && (
        <div style={{ background: "var(--bg-warning)", border: "0.5px solid var(--border-warning)", borderRadius: 12, padding: "14px 18px", marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text-warning)", marginBottom: 8 }}>
            Alertas detectadas
          </div>
          <ul style={{ margin: 0, padding: "0 0 0 16px" }}>
            {r.alerts.map((a, i) => <li key={i} style={{ fontSize: 13, color: "var(--text-warning)", marginBottom: 2 }}>{a}</li>)}
          </ul>
        </div>
      )}

      {r.weekly.length > 0 && (
        <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16, marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Actividad semanal de commits</div>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={r.weekly} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
              <XAxis dataKey="w" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip formatter={v => [v, "Commits"]} />
              <Bar dataKey="n" radius={[3, 3, 0, 0]}>
                {r.weekly.map((d, i) => (
                  <Cell key={i} fill={d.n === 0 ? "var(--surface-0)" : d.n >= 3 ? "#22C55E" : "#3B82F6"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {Object.keys(r.struct.files).length > 0 && (
        <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, padding: 16, marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 10 }}>Archivos requeridos</div>
          {Object.entries(r.struct.files).map(([file, present]) => (
            <div key={file} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "8px 12px", borderRadius: 6, marginBottom: 4,
              background: present ? "var(--bg-success)" : "var(--bg-danger)",
              border: `0.5px solid ${present ? "var(--border-success)" : "var(--border-danger)"}`,
            }}>
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: present ? "var(--text-success)" : "var(--text-danger)" }}>{file}</code>
              <span style={{ fontSize: 12, fontWeight: 500, color: present ? "var(--text-success)" : "var(--text-danger)" }}>{present ? "Presente" : "Ausente"}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
        {reportUrl && (
          <a href={reportUrl} target="_blank" rel="noreferrer" style={{
            padding: "8px 16px", fontSize: 13, background: "var(--fill-accent)", color: "var(--on-accent)",
            border: "none", borderRadius: 8, cursor: "pointer", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6
          }}>
            Ver informe HTML
          </a>
        )}
      </div>
    </div>
  );
}

// ─── Vista Reportes ───────────────────────────────────────────────────────────
function ReportesView({ results, evaluationId, setView }) {
  const [selected, setSelected] = useState(null);

  if (selected) return <ReporteDetalle r={selected} evaluationId={evaluationId} onBack={() => setSelected(null)} />;

  if (!results.length) return (
    <div style={{ padding: 24, textAlign: "center", paddingTop: 60 }}>
      <h3 style={{ margin: "0 0 8px", fontWeight: 500 }}>Sin evaluaciones disponibles</h3>
      <p style={{ margin: "0 0 20px", color: "var(--text-secondary)" }}>Ejecuta una evaluación primero para ver los reportes.</p>
      <button onClick={() => setView("evaluacion")} style={{ fontSize: 13, padding: "8px 20px", background: "var(--fill-accent)", color: "var(--on-accent)", border: "none", cursor: "pointer", borderRadius: 8 }}>
        Ir a evaluación
      </button>
    </div>
  );

  const passing = results.filter(r => r.score >= 70).length;
  const risk    = results.filter(r => r.score >= 50 && r.score < 70).length;
  const failing = results.filter(r => r.score < 50).length;

  return (
    <div style={{ padding: 24, maxWidth: 580 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 20 }}>
        {[
          { label: "Total", value: results.length, color: undefined },
          { label: "Aprobados ≥70", value: passing, color: "var(--text-success)" },
          { label: "En riesgo 50–70", value: risk, color: "var(--text-warning)" },
          { label: "Reprobados <50", value: failing, color: "var(--text-danger)" },
        ].map(s => (
          <div key={s.label} style={{ background: "var(--surface-1)", borderRadius: 8, padding: 12, textAlign: "center" }}>
            <div style={{ fontSize: 22, fontWeight: 500, color: s.color || "var(--text-primary)" }}>{s.value}</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      <div style={{ background: "var(--surface-2)", border: "0.5px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: "12px 18px", borderBottom: "0.5px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 500, fontSize: 13 }}>Resultados del grupo</span>
          <div style={{ display: "flex", gap: 8 }}>
            {evaluationId && (
              <a href={`${API_BASE}/reports/${evaluationId}`} target="_blank" rel="noreferrer"
                style={{ fontSize: 12, padding: "4px 12px", textDecoration: "none", color: "var(--text-primary)", border: "0.5px solid var(--border)", borderRadius: 6, background: "var(--surface-2)", display: "inline-flex", alignItems: "center", gap: 4 }}>
                Consolidado HTML
              </a>
            )}
          </div>
        </div>

        {results.map((r, i) => (
          <div key={r.id || i} onClick={() => setSelected(r)}
            style={{
              display: "flex", alignItems: "center", gap: 12, padding: "12px 18px",
              background: i % 2 === 0 ? "transparent" : "var(--surface-1)",
              borderBottom: i < results.length - 1 ? "0.5px solid var(--border)" : "none",
              cursor: "pointer",
            }}
            onMouseOver={e => e.currentTarget.style.background = "var(--surface-1)"}
            onMouseOut={e => e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "var(--surface-1)"}
          >
            <div style={{ width: 44, height: 44, borderRadius: "50%", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: scoreBg(r.score), border: `2px solid ${scoreBdr(r.score)}` }}>
              <span style={{ fontWeight: 500, fontSize: 14, color: scoreColor(r.score) }}>{r.score}</span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 500, fontSize: 13 }}>{r.student}</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{r.repo}</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end", flexShrink: 0 }}>
              <PatternBadge pattern={r.pattern} pColor={r.pColor} />
              {r.alerts.length > 0 && (
                <span style={{ fontSize: 11, color: "var(--text-warning)" }}>
                  {r.alerts.length} alerta{r.alerts.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── App root ─────────────────────────────────────────────────────────────────
export default function App() {
  const [view, setView] = useState("inicio");
  const [results, setResults] = useState([]);
  const [evaluationId, setEvaluationId] = useState(null);

  const handleDone = (newResults, evId) => {
    setResults(newResults);
    setEvaluationId(evId);
    setView("reportes");
  };

  const NAV = [
    { id: "inicio", icon: "home", label: "Inicio" },
    { id: "criterios", icon: "settings", label: "Criterios" },
    { id: "evaluacion", icon: "player-play", label: "Evaluación" },
    { id: "reportes", icon: "chart-bar", label: "Reportes" },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "var(--font-sans)", background: "var(--surface-0)" }}>
      <h2 style={{ position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0,0,0,0)", border: 0 }}>
        EvalRepo — Sistema multi-agente de evaluación de repositorios GitHub estudiantiles
      </h2>

      {/* Sidebar */}
      <div style={{ width: 175, background: NAVY, display: "flex", flexDirection: "column", flexShrink: 0, minHeight: "100vh" }}>
        <div style={{ padding: 16, borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 7, background: "rgba(255,255,255,0.12)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: "white" }}>ER</span>
            </div>
            <div>
              <div style={{ color: "white", fontWeight: 500, fontSize: 14, lineHeight: 1.1 }}>EvalRepo</div>
              <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 10 }}>UTPL · TIC 2025</div>
            </div>
          </div>
        </div>

        <nav style={{ flex: 1, padding: "10px 8px", display: "flex", flexDirection: "column", gap: 2 }} aria-label="Navegación principal">
          {NAV.map(item => (
            <NavItem key={item.id} {...item} active={view === item.id} onClick={() => setView(item.id)} />
          ))}
        </nav>

        <div style={{ padding: "12px 16px", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0, background: results.length ? "#34D399" : "rgba(255,255,255,0.25)" }} />
            <span style={{ color: "rgba(255,255,255,0.35)", fontSize: 11 }}>
              {results.length ? `${results.length} repos evaluados` : "Sin evaluaciones"}
            </span>
          </div>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, overflow: "auto" }}>
        <div style={{ background: "var(--surface-2)", borderBottom: "0.5px solid var(--border)", padding: "12px 24px", position: "sticky", top: 0, zIndex: 10 }}>
          <div style={{ fontSize: 15, fontWeight: 500 }}>
            {view === "inicio" && "Inicio"}
            {view === "criterios" && "Criterios de evaluación"}
            {view === "evaluacion" && "Nueva evaluación"}
            {view === "reportes" && "Reportes"}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {view === "inicio" && "Sistema multi-agente para asistencia docente — UTPL Computación"}
            {view === "criterios" && "Configura criterios y pesos antes de ejecutar una evaluación"}
            {view === "evaluacion" && "Ingresa las URLs de los repositorios estudiantiles y ejecuta el análisis"}
            {view === "reportes" && "Resultados de la última evaluación ejecutada"}
          </div>
        </div>

        {view === "inicio" && <InicioView setView={setView} />}
        {view === "criterios" && <CriteriosView />}
        {view === "evaluacion" && <EvaluacionView onDone={handleDone} />}
        {view === "reportes" && <ReportesView results={results} evaluationId={evaluationId} setView={setView} />}
      </div>
    </div>
  );
}
