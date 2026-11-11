/**
 * App.jsx — EvalRepo Frontend
 * SMA · Evaluación de Repositorios UTPL
 *
 * Instalar dependencias adicionales:
 *   npm install recharts
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import yaml from 'js-yaml'

// ─── Configuración ────────────────────────────────────────────────────────────
const API_BASE = 'http://localhost:8000'

// ─── Paleta de colores ────────────────────────────────────────────────────────
const C = {
  navy:      '#1B3A5C',
  navyDark:  '#142E49',
  blue:      '#2563EB',
  blueSoft:  '#EFF6FF',
  green:     '#16A34A',
  greenSoft: '#F0FDF4',
  greenBdr:  '#BBF7D0',
  amber:     '#D97706',
  amberSoft: '#FFFBEB',
  amberBdr:  '#FDE68A',
  red:       '#DC2626',
  redSoft:   '#FEF2F2',
  redBdr:    '#FECACA',
  gray:      '#64748B',
  grayLight: '#F1F5F9',
  border:    '#E2E8F0',
  white:     '#FFFFFF',
  text:      '#0F172A',
  textSub:   '#64748B',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const scoreColor = s => s >= 70 ? C.green : s >= 50 ? C.amber : C.red
const scoreSoft  = s => s >= 70 ? C.greenSoft : s >= 50 ? C.amberSoft : C.redSoft
const scoreBdr   = s => s >= 70 ? C.greenBdr : s >= 50 ? C.amberBdr : C.redBdr

const normalizeResult = r => {
  const vr = r.versioning_result || {}
  const tr = r.temporal_result   || {}
  const sr = r.structural_result || {}
  const cr = r.content_result    || {}
  const score = parseFloat(r.global_score) || 0

  // Fechas reales de cada semana en vez de "Sem 1" — fallback a weekly_counts
  // por si el backend todavía no manda weekly_breakdown (compatibilidad hacia atrás).
  const weekly = (tr.weekly_breakdown && tr.weekly_breakdown.length > 0)
    ? tr.weekly_breakdown.map(w => ({
        w: `${w.start_date.slice(5)} al ${w.end_date.slice(5)}`,
        range: `${w.start_date} — ${w.end_date}`,
        n: w.count,
      }))
    : Object.entries(tr.weekly_counts || {})
        .sort(([a],[b]) => a.localeCompare(b))
        .map(([,n], i) => ({ w: `Sem ${i+1}`, range: '', n }))

  const filesMap = {}
  ;(sr.files_found   || []).forEach(f => { filesMap[f] = true })
  ;(sr.files_missing || []).forEach(f => { filesMap[f] = false })

  return {
    id: r.id, student: r.student, repo: r.repo_name, url: r.url, score,
    pattern: r.pattern_label || 'Sin datos',
    status: score >= 70 ? 'ok' : score >= 50 ? 'alerta' : 'falla',
    onTime: tr.on_time ?? false,
    lastCommitDate: tr.last_commit_date ?? null,
    commits: vr.total_commits ?? 0,
    branches: vr.branch_count ?? 0,
    quality: vr.quality_pct ?? 0,
    genericMessages: vr.generic_messages || [],
    contributors: vr.contributors || [],
    commitLog: vr.commit_log || [],
    alerts: r.alerts || [],
    scoreOverridden: r.score_overridden ?? false,
    originalScore: r.original_score ?? null,
    overrideNote: r.override_note ?? null,
    weekly,
    struct: {
      score: sr.score ?? 0, max: sr.max_score ?? 25,
      ok: (sr.score ?? 0) >= (sr.max_score ?? 25) * 0.6,
      files: filesMap,
      readmeChars: sr.readme_char_count ?? 0,
      readmeOk: sr.readme_ok ?? false,
      branchChecks: sr.branch_checks || [],
      alternativeChecks: sr.alternative_checks || [],
    },
    versioning: {
      score: vr.score ?? 0, max: vr.max_score ?? 40,
      ok: vr.commits_ok && vr.branches_ok && vr.quality_ok,
      commitsOk: vr.commits_ok ?? false,
      branchesOk: vr.branches_ok ?? false,
      qualityOk: vr.quality_ok ?? false,
      commitsMin: vr.details?.commits_min ?? 10,
      ramasMin: vr.details?.min_ramas ?? 2,
      qualityUmbral: vr.details?.quality_umbral ?? 70,
    },
    temporal: {
      score: tr.score ?? 0, max: tr.max_score ?? 25,
      ok: !tr.concentration_alert && tr.activity_ok,
      concentrationAlert: tr.concentration_alert ?? false,
      concentrationPct: tr.concentration_pct ?? 0,
      activityOk: tr.activity_ok ?? false,
      activeWeeks: tr.active_weeks ?? 0,
      totalWeeks: tr.total_weeks ?? 0,
    },
    content: {
      score: cr.score ?? 0, max: cr.max_score ?? 10,
      ok: (cr.coherence_level ?? '') === 'Alta',
      coherence: cr.coherence_level ?? 'N/A',
      summary: cr.llm_summary ?? '',
      found: cr.requirements_found || [],
      missing: cr.requirements_missing || [],
      requirementScores: cr.details?.requirement_scores || null,
      requisitosPesos: cr.details?.requisitos_pesos || null,
      branchRequirements: cr.branch_requirements || [],
    },
    error: r.error || null,
  }
}

// ─── Componentes base ─────────────────────────────────────────────────────────

const Badge = ({ type, children, style }) => {
  const map = {
    ok:          { bg: C.greenSoft, color: C.green,  bdr: C.greenBdr },
    alerta:      { bg: C.amberSoft, color: C.amber,  bdr: C.amberBdr },
    falla:       { bg: C.redSoft,   color: C.red,    bdr: C.redBdr   },
    completado:  { bg: C.greenSoft, color: C.green,  bdr: C.greenBdr },
    procesando:  { bg: C.blueSoft,  color: C.blue,   bdr: '#BFDBFE'  },
    pendiente:   { bg: '#F8FAFC',   color: C.gray,   bdr: C.border   },
    error:       { bg: C.redSoft,   color: C.red,    bdr: C.redBdr   },
    activo:      { bg: C.blueSoft,  color: C.blue,   bdr: '#BFDBFE'  },
    listo:       { bg: C.greenSoft, color: C.green,  bdr: C.greenBdr },
  }
  const s = map[type] || map.pendiente
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 999,
      fontSize: 12, fontWeight: 600,
      background: s.bg, color: s.color, border: `1px solid ${s.bdr}`,
      ...style
    }}>{children}</span>
  )
}

const Toggle = ({ checked, onChange }) => (
  <button onClick={() => onChange(!checked)} style={{
    width: 40, height: 22, borderRadius: 11, border: 'none', cursor: 'pointer',
    background: checked ? C.blue : C.border, position: 'relative', transition: 'background 0.2s',
    flexShrink: 0,
  }}>
    <div style={{
      width: 16, height: 16, borderRadius: '50%', background: C.white,
      position: 'absolute', top: 3, left: checked ? 21 : 3, transition: 'left 0.2s',
    }} />
  </button>
)

const Tag = ({ label, onRemove }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '2px 8px', borderRadius: 6, fontSize: 12,
    background: C.grayLight, color: C.text, border: `1px solid ${C.border}`,
  }}>
    {label}
    {onRemove && (
      <button onClick={onRemove} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: C.gray, fontSize: 14, lineHeight: 1, padding: 0
      }}>×</button>
    )}
  </span>
)

const SectionCard = ({ title, children }) => (
  <div style={{
    background: C.white, border: `1px solid ${C.border}`,
    borderRadius: 10, padding: '20px 24px', marginBottom: 16,
  }}>
    <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: C.text }}>{title}</h3>
    {children}
  </div>
)

const FieldRow = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}>
    <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: C.textSub, marginBottom: 5 }}>
      {label}
    </label>
    {children}
  </div>
)

const Input = ({ ...props }) => (
  <input {...props} style={{
    width: '100%', padding: '8px 10px', borderRadius: 7,
    border: `1px solid ${C.border}`, fontSize: 13, boxSizing: 'border-box',
    outline: 'none', color: C.text, background: C.white,
    ...props.style
  }} />
)

const Btn = ({ variant = 'primary', children, ...props }) => {
  const styles = {
    primary: { background: C.blue, color: C.white, border: 'none' },
    secondary: { background: C.white, color: C.text, border: `1px solid ${C.border}` },
    danger: { background: C.redSoft, color: C.red, border: `1px solid ${C.redBdr}` },
    ghost: { background: 'transparent', color: C.blue, border: 'none' },
  }
  return (
    <button {...props} style={{
      padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 500,
      cursor: props.disabled ? 'not-allowed' : 'pointer',
      opacity: props.disabled ? 0.5 : 1,
      display: 'inline-flex', alignItems: 'center', gap: 6,
      ...styles[variant], ...props.style
    }}>{children}</button>
  )
}

// ─── Modal de pesos ───────────────────────────────────────────────────────────
const WeightsModal = ({ weights, onChange, onClose }) => {
  const [local, setLocal] = useState({ ...weights })
  const total = Object.values(local).reduce((a,b) => a+b, 0)
  const ok = total === 100

  const dims = [
    { key: 'estructural', label: 'Estructural' },
    { key: 'versionado',  label: 'Versionado'  },
    { key: 'temporal',    label: 'Temporal'     },
    { key: 'contenido',   label: 'Contenido'    },
  ]

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: C.white, borderRadius: 12, padding: 28, width: 380, boxShadow: '0 8px 32px rgba(0,0,0,0.15)'
      }}>
        <h3 style={{ margin: '0 0 6px', fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
          Ajustar pesos de las dimensiones
        </h3>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: C.textSub }}>
          La suma actual de los pesos es {total}%. Ajusta los valores para que el total sea exactamente 100% antes de guardar.
        </p>
        {dims.map(({ key, label }) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <span style={{ width: 90, fontSize: 13 }}>{label}</span>
            <Input
              type="number" min={0} max={100}
              value={local[key]}
              onChange={e => setLocal(p => ({ ...p, [key]: +e.target.value }))}
              style={{ width: 70 }}
            />
            <span style={{ fontSize: 13, color: C.textSub }}>%</span>
          </div>
        ))}
        <div style={{
          padding: '6px 12px', borderRadius: 6, marginBottom: 20, fontSize: 13, fontWeight: 600,
          background: ok ? C.greenSoft : C.redSoft,
          color: ok ? C.green : C.red,
          border: `1px solid ${ok ? C.greenBdr : C.redBdr}`,
        }}>
          Suma total: {total}% {ok ? '(correcto)' : `— falta ${100-total}%`}
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Btn variant="secondary" onClick={onClose}>Cancelar</Btn>
          <Btn disabled={!ok} onClick={() => { onChange(local); onClose() }}>
            Guardar {!ok && '(deshabilitado)'}
          </Btn>
        </div>
      </div>
    </div>
  )
}

// ─── Vista: Criterios ─────────────────────────────────────────────────────────
const DEFAULT_GENERIC = ['update', 'fix', 'changes', 'wip', 'test']
const DEFAULT_FILES   = ['README.md', '.env', 'requirements.txt', '/docs']
const DEFAULT_CONTENIDO = {
  requisitos: [
    { texto: 'Implementar al menos 3 clases con herencia entre ellas', peso_pct: null },
    { texto: 'Usar al menos 1 patrón de diseño (Factory, Singleton, Observer, etc.)', peso_pct: null },
    { texto: 'Aplicar al menos 2 principios SOLID de forma explícita', peso_pct: null },
  ],
  extensiones: ['.py', '.java', '.js', '.ts', '.cpp', '.cs'],
  maxArchivos: 10,
}
// Normaliza un requisito (puede venir como string viejo, o como {texto, peso_pct})
const normReq = r => typeof r === 'string' ? { texto: r, peso_pct: null } : { texto: r.texto, peso_pct: r.peso_pct ?? null }
const DEFAULT_QUALITY_UMBRAL = 70

// Convierte una palabra simple en un patrón regex anclado (^palabra$) para que
// coincida con lo que espera el backend; si el docente ya escribió un regex
// (empieza con ^ o trae \), se respeta tal cual.
const toGenericPattern = w => {
  if (w.startsWith('^') || w.includes('\\')) return w
  return `^${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`
}

// Arma el objeto de criterios (con la misma forma que config/default.yaml) que
// se manda al backend y que también se exporta/importa como archivo YAML.
const buildCriteriaPayload = ui => ({
  periodo: {
    inicio: ui.periodStart,
    fin: ui.periodEnd,
    fecha_limite: ui.deadline.length === 16 ? `${ui.deadline}:00` : ui.deadline,
  },
  estructural: {
    habilitado: ui.dims.estructural,
    peso: ui.weights.estructural,
    archivos_requeridos: ui.files,
    readme_min_chars: ui.readmeMin,
    archivos_por_rama: ui.archivosPorRama.reduce((acc, { branch, path }) => {
      if (!branch || !path) return acc
      acc[branch] = [...(acc[branch] || []), path]
      return acc
    }, {}),
    archivos_alternativos: ui.archivosAlternativos
      .filter(a => a.nombre && a.carpetas.length > 0)
      .map(a => ({ nombre: a.nombre, carpetas: a.carpetas })),
  },
  versionado: {
    habilitado: ui.dims.versionado,
    peso: ui.weights.versionado,
    commits_min: ui.commitsMin,
    calidad_mensajes: {
      habilitado: true,
      umbral_porcentaje: ui.qualityUmbral,
      patrones_genericos: ui.generic.map(toGenericPattern),
    },
    ramas: { habilitado: true, min_ramas: ui.ramasMin },
  },
  temporal: {
    habilitado: ui.dims.temporal,
    peso: ui.weights.temporal,
    actividad_minima_semanal: true,
    alerta_concentracion: {
      habilitado: true,
      dias_finales: ui.concDias,
      porcentaje_umbral: ui.concUmbral,
    },
  },
  contenido: {
    habilitado: ui.dims.contenido,
    peso: ui.weights.contenido,
    requisitos_funcionales: ui.contenido.requisitos.map(r => (
      r.peso_pct == null ? r.texto : { texto: r.texto, peso_pct: +r.peso_pct }
    )),
    extensiones_codigo: ui.contenido.extensiones,
    max_archivos: ui.contenido.maxArchivos,
    requisitos_por_rama: ui.requisitosPorRama
      .filter(g => g.rama && g.requisitos.length > 0)
      .map(g => ({
        rama: g.rama,
        archivos: g.archivos,
        requisitos: g.requisitos.map(r => (
          r.peso_pct == null ? r.texto : { texto: r.texto, peso_pct: +r.peso_pct }
        )),
      })),
  },
})

// El camino inverso: de un objeto de criterios (cargado de un YAML o de una
// config guardada) a los campos sueltos que usa la interfaz.
const criteriaToUI = c => ({
  weights: {
    estructural: c.estructural?.peso ?? 25,
    versionado: c.versionado?.peso ?? 40,
    temporal: c.temporal?.peso ?? 25,
    contenido: c.contenido?.peso ?? 10,
  },
  dims: {
    estructural: c.estructural?.habilitado ?? true,
    versionado: c.versionado?.habilitado ?? true,
    temporal: c.temporal?.habilitado ?? true,
    contenido: c.contenido?.habilitado ?? true,
  },
  files: c.estructural?.archivos_requeridos ?? DEFAULT_FILES,
  readmeMin: c.estructural?.readme_min_chars ?? 500,
  archivosPorRama: Object.entries(c.estructural?.archivos_por_rama ?? {})
    .flatMap(([branch, paths]) => paths.map(path => ({ branch, path }))),
  archivosAlternativos: (c.estructural?.archivos_alternativos ?? [])
    .map(a => ({ nombre: a.nombre, carpetas: a.carpetas })),
  commitsMin: c.versionado?.commits_min ?? 10,
  ramasMin: c.versionado?.ramas?.min_ramas ?? 2,
  qualityUmbral: c.versionado?.calidad_mensajes?.umbral_porcentaje ?? DEFAULT_QUALITY_UMBRAL,
  generic: (c.versionado?.calidad_mensajes?.patrones_genericos ?? DEFAULT_GENERIC)
    .map(p => p.replace(/^\^/, '').replace(/\$$/, '')),
  deadline: (c.periodo?.fecha_limite ?? '2026-08-31T23:59:00').slice(0, 16),
  periodStart: c.periodo?.inicio ?? '2024-08-01',
  periodEnd: c.periodo?.fin ?? '2026-12-31',
  concUmbral: c.temporal?.alerta_concentracion?.porcentaje_umbral ?? 60,
  concDias: c.temporal?.alerta_concentracion?.dias_finales ?? 3,
  contenido: {
    requisitos: (c.contenido?.requisitos_funcionales ?? DEFAULT_CONTENIDO.requisitos).map(normReq),
    extensiones: c.contenido?.extensiones_codigo ?? DEFAULT_CONTENIDO.extensiones,
    maxArchivos: c.contenido?.max_archivos ?? DEFAULT_CONTENIDO.maxArchivos,
  },
  requisitosPorRama: (c.contenido?.requisitos_por_rama ?? []).map(g => ({
    rama: g.rama, archivos: g.archivos ?? ['README.md'],
    requisitos: (g.requisitos ?? []).map(normReq),
  })),
})

function CriteriosView({
  weights, setWeights, contenido, setContenido,
  dims, setDims, files, setFiles, readmeMin, setReadmeMin,
  commitsMin, setCommitsMin, ramasMin, setRamasMin,
  qualityUmbral, setQualityUmbral, generic, setGeneric,
  deadline, setDeadline, periodStart, setPeriodStart,
  periodEnd, setPeriodEnd, concUmbral, setConcUmbral,
  concDias, setConcDias,
  archivosPorRama, setArchivosPorRama,
  archivosAlternativos, setArchivosAlternativos,
  requisitosPorRama, setRequisitosPorRama,
}) {
  const [newFile, setNewFile]   = useState('')
  const [newGeneric, setNewGeneric] = useState('')
  const [interval, setInterval]       = useState('semana')
  const [newRequisito, setNewRequisito] = useState('')
  const [newExt, setNewExt]           = useState('')
  const [newRamaBranch, setNewRamaBranch] = useState('')
  const [newRamaPath, setNewRamaPath]     = useState('')
  const [newAltNombre, setNewAltNombre]   = useState('')
  const [newAltCarpetas, setNewAltCarpetas] = useState('')
  const [newGrupoRama, setNewGrupoRama]   = useState('')
  const [newGrupoArchivos, setNewGrupoArchivos] = useState('README.md')
  const [newGrupoReqTexto, setNewGrupoReqTexto] = useState({})
  const [configName, setConfigName]   = useState('')
  const [importError, setImportError] = useState('')
  const yamlInputRef = useRef(null)
  const [savedConfigs, setSavedConfigs] = useState(() => {
    try { return JSON.parse(localStorage.getItem('evalrepo_configs') || '[]') }
    catch { return [] }
  })
  const [showWeightsModal, setShowWeightsModal] = useState(false)

  const total = Object.values(weights).reduce((a,b) => a+b, 0)

  const saveConfig = () => {
    if (!configName.trim()) return
    const config = {
      name: configName, date: new Date().toISOString().slice(0,10),
      weights, dims, files, readmeMin, commitsMin, ramasMin, qualityUmbral,
      generic, deadline, periodStart, periodEnd, interval, concUmbral, concDias,
      contenido, archivosPorRama, archivosAlternativos, requisitosPorRama,
    }
    const updated = [...savedConfigs.filter(c => c.name !== configName), config]
    setSavedConfigs(updated)
    localStorage.setItem('evalrepo_configs', JSON.stringify(updated))
    setConfigName('')
  }

  const loadConfig = c => {
    setWeights(c.weights || weights)
    setDims(c.dims || dims)
    setFiles(c.files || files)
    setReadmeMin(c.readmeMin || 500)
    setCommitsMin(c.commitsMin || 10)
    setRamasMin(c.ramasMin || 2)
    setQualityUmbral(c.qualityUmbral || DEFAULT_QUALITY_UMBRAL)
    setGeneric(c.generic || DEFAULT_GENERIC)
    setDeadline(c.deadline || deadline)
    setPeriodStart(c.periodStart || periodStart)
    setPeriodEnd(c.periodEnd || periodEnd)
    setInterval(c.interval || 'semana')
    setConcUmbral(c.concUmbral || 60)
    setConcDias(c.concDias || 3)
    setContenido(c.contenido || DEFAULT_CONTENIDO)
    setArchivosPorRama(c.archivosPorRama || [])
    setArchivosAlternativos(c.archivosAlternativos || [])
    setRequisitosPorRama(c.requisitosPorRama || [])
  }

  const addRequisito = () => {
    const r = newRequisito.trim()
    if (!r || contenido.requisitos.some(x => x.texto === r)) return
    setContenido(p => ({ ...p, requisitos: [...p.requisitos, { texto: r, peso_pct: null }] }))
    setNewRequisito('')
  }

  const setRequisitoPeso = (i, value) => setContenido(p => ({
    ...p,
    requisitos: p.requisitos.map((r, idx) => idx === i ? { ...r, peso_pct: value === '' ? null : +value } : r),
  }))

  // Suma lo que el docente asignó a mano (código + todas las ramas juntas) — todos
  // comparten el mismo presupuesto: el peso que le diste a la dimensión Contenido.
  const pesoAsignadoContenido = contenido.requisitos.reduce((a, r) => a + (r.peso_pct || 0), 0)
    + requisitosPorRama.reduce((a, g) => a + g.requisitos.reduce((a2, r) => a2 + (r.peso_pct || 0), 0), 0)

  // Grupos de "requisitos por rama" — ej. "el README de la rama 'prompts' debe
  // documentar los prompts usados para generar el proyecto"
  const addGrupoRama = () => {
    const rama = newGrupoRama.trim()
    const archivos = newGrupoArchivos.split(',').map(s => s.trim()).filter(Boolean)
    if (!rama || archivos.length === 0 || requisitosPorRama.some(g => g.rama === rama)) return
    setRequisitosPorRama(p => [...p, { rama, archivos, requisitos: [] }])
    setNewGrupoRama(''); setNewGrupoArchivos('README.md')
  }

  const addRequisitoGrupo = (gi) => {
    const texto = (newGrupoReqTexto[gi] || '').trim()
    if (!texto) return
    setRequisitosPorRama(p => p.map((g, idx) => idx === gi
      ? { ...g, requisitos: [...g.requisitos, { texto, peso_pct: null }] }
      : g))
    setNewGrupoReqTexto(p => ({ ...p, [gi]: '' }))
  }

  const setRequisitoGrupoPeso = (gi, ri, value) => setRequisitosPorRama(p => p.map((g, idx) => idx !== gi ? g : {
    ...g,
    requisitos: g.requisitos.map((r, idx2) => idx2 === ri ? { ...r, peso_pct: value === '' ? null : +value } : r),
  }))

  const addExt = () => {
    let e = newExt.trim()
    if (!e) return
    if (!e.startsWith('.')) e = '.' + e
    if (!contenido.extensiones.includes(e)) setContenido(p => ({ ...p, extensiones: [...p.extensiones, e] }))
    setNewExt('')
  }

  const deleteConfig = name => {
    const updated = savedConfigs.filter(c => c.name !== name)
    setSavedConfigs(updated)
    localStorage.setItem('evalrepo_configs', JSON.stringify(updated))
  }

  // RF-03: reutilizar la configuración de criterios entre asignaturas y ciclos
  // como archivo YAML — el mismo formato que usa el backend (config/default.yaml),
  // así el docente puede llevárselo, editarlo a mano o usarlo con demo.py --criteria.
  const exportYAML = () => {
    const current = buildCriteriaPayload({
      weights, dims, files, readmeMin, commitsMin, ramasMin, qualityUmbral,
      generic, deadline, periodStart, periodEnd, concUmbral, concDias, contenido,
      archivosPorRama, archivosAlternativos, requisitosPorRama,
    })
    const text = `# Criterios de evaluación — EvalRepo\n# Exportado desde el Módulo de Configuración de Criterios\n${yaml.dump(current, { lineWidth: -1 })}`
    const blob = new Blob([text], { type: 'application/x-yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(configName || 'criterios-evalrepo').trim().replace(/\s+/g, '_')}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importYAML = e => {
    const file = e.target.files[0]
    if (!file) return
    setImportError('')
    const reader = new FileReader()
    reader.onload = ev => {
      try {
        const parsed = yaml.load(ev.target.result)
        const ui = criteriaToUI(parsed || {})
        setWeights(ui.weights); setDims(ui.dims); setFiles(ui.files)
        setReadmeMin(ui.readmeMin); setCommitsMin(ui.commitsMin); setRamasMin(ui.ramasMin)
        setQualityUmbral(ui.qualityUmbral); setGeneric(ui.generic)
        setDeadline(ui.deadline); setPeriodStart(ui.periodStart); setPeriodEnd(ui.periodEnd)
        setConcUmbral(ui.concUmbral); setConcDias(ui.concDias)
        setContenido(ui.contenido)
        setArchivosPorRama(ui.archivosPorRama); setArchivosAlternativos(ui.archivosAlternativos)
        setRequisitosPorRama(ui.requisitosPorRama)
      } catch (err) {
        setImportError('No se pudo leer el archivo: ' + err.message)
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const DimRow = ({ key: k, label, desc }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
      <Toggle checked={dims[k]} onChange={v => setDims(p => ({...p, [k]: v}))} />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: 12, color: C.textSub }}>{desc}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Input type="number" min={0} max={100} value={weights[k]}
          onChange={e => setWeights(p => ({...p, [k]: +e.target.value}))}
          style={{ width: 60, textAlign: 'right' }}
        />
        <span style={{ fontSize: 13, color: C.textSub }}>%</span>
      </div>
    </div>
  )

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: '24px 24px 48px' }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 4px' }}>Configuración de Criterios</h2>
      <p style={{ fontSize: 13, color: C.textSub, margin: '0 0 24px' }}>
        Define las dimensiones de evaluación, sus pesos y los umbrales que aplicará el sistema multi-agente.
      </p>

      {/* Dimensiones */}
      <SectionCard title="Dimensiones de evaluación">
        {[
          { k: 'estructural', label: 'Estructural', desc: 'Presencia de archivos y documentación requerida' },
          { k: 'versionado',  label: 'Versionado',  desc: 'Frecuencia de commits, mensajes y ramas' },
          { k: 'temporal',    label: 'Temporal',    desc: 'Distribución de la actividad en el tiempo' },
          { k: 'contenido',   label: 'Contenido',   desc: 'Calidad y coherencia del código entregado' },
        ].map(({ k, label, desc }) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
            <Toggle checked={dims[k]} onChange={v => setDims(p => ({...p, [k]: v}))} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
              <div style={{ fontSize: 12, color: C.textSub }}>{desc}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Input type="number" min={0} max={100} value={weights[k]}
                onChange={e => setWeights(p => ({...p, [k]: +e.target.value}))}
                style={{ width: 60, textAlign: 'right' }}
              />
              <span style={{ fontSize: 13, color: C.textSub }}>%</span>
            </div>
          </div>
        ))}
        <div style={{
          marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between'
        }}>
          <span style={{ fontSize: 13, color: C.textSub }}>Suma total de pesos:</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              padding: '3px 12px', borderRadius: 999, fontSize: 13, fontWeight: 600,
              background: total === 100 ? C.greenSoft : C.redSoft,
              color: total === 100 ? C.green : C.red,
            }}>{total}% {total === 100 ? 'correcto' : 'incompleto'}</span>
            {total !== 100 && (
              <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px' }}
                onClick={() => setShowWeightsModal(true)}>
                Ajustar pesos
              </Btn>
            )}
          </div>
        </div>
      </SectionCard>

      {/* Criterios Estructurales */}
      {dims.estructural && (
        <SectionCard title="Criterios Estructurales">
          <FieldRow label="Archivos y carpetas requeridas">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
              {files.map(f => (
                <Tag key={f} label={f} onRemove={() => setFiles(p => p.filter(x => x !== f))} />
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input placeholder="ej. CONTRIBUTING.md" value={newFile}
                onChange={e => setNewFile(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && newFile.trim()) { setFiles(p => [...p, newFile.trim()]); setNewFile('') }}}
                style={{ flex: 1 }}
              />
              <Btn variant="secondary" onClick={() => { if (newFile.trim()) { setFiles(p => [...p, newFile.trim()]); setNewFile('') }}}>
                + Agregar
              </Btn>
            </div>
          </FieldRow>
          <FieldRow label="Umbral mínimo de documentación (caracteres)">
            <Input type="number" value={readmeMin} onChange={e => setReadmeMin(+e.target.value)} style={{ width: 160 }} />
          </FieldRow>

          <FieldRow label="Archivos requeridos en una rama específica (ej. README en 'docs', código en 'main')">
            {archivosPorRama.map((r, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0' }}>
                <span style={{ fontSize: 13, flex: 1 }}><code>{r.path}</code> en rama <code>{r.branch}</code></span>
                <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px', color: C.red }}
                  onClick={() => setArchivosPorRama(p => p.filter((_, idx) => idx !== i))}>Quitar</Btn>
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <Input placeholder="rama (ej. docs)" value={newRamaBranch}
                onChange={e => setNewRamaBranch(e.target.value)} style={{ width: 140 }} />
              <Input placeholder="archivo o carpeta (ej. README.md)" value={newRamaPath}
                onChange={e => setNewRamaPath(e.target.value)} style={{ flex: 1 }} />
              <Btn variant="secondary" onClick={() => {
                if (newRamaBranch.trim() && newRamaPath.trim()) {
                  setArchivosPorRama(p => [...p, { branch: newRamaBranch.trim(), path: newRamaPath.trim() }])
                  setNewRamaBranch(''); setNewRamaPath('')
                }
              }}>+ Agregar</Btn>
            </div>
          </FieldRow>

          <FieldRow label="Archivo que debe existir en alguna de varias carpetas posibles">
            {archivosAlternativos.map((a, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0' }}>
                <span style={{ fontSize: 13, flex: 1 }}><code>{a.nombre}</code> en {a.carpetas.join(' ó ')}</span>
                <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px', color: C.red }}
                  onClick={() => setArchivosAlternativos(p => p.filter((_, idx) => idx !== i))}>Quitar</Btn>
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <Input placeholder="nombre de archivo (ej. config.py)" value={newAltNombre}
                onChange={e => setNewAltNombre(e.target.value)} style={{ width: 200 }} />
              <Input placeholder="carpetas separadas por coma (ej. src/, app/)" value={newAltCarpetas}
                onChange={e => setNewAltCarpetas(e.target.value)} style={{ flex: 1 }} />
              <Btn variant="secondary" onClick={() => {
                const carpetas = newAltCarpetas.split(',').map(s => s.trim()).filter(Boolean)
                if (newAltNombre.trim() && carpetas.length > 0) {
                  setArchivosAlternativos(p => [...p, { nombre: newAltNombre.trim(), carpetas }])
                  setNewAltNombre(''); setNewAltCarpetas('')
                }
              }}>+ Agregar</Btn>
            </div>
          </FieldRow>
        </SectionCard>
      )}

      {/* Criterios de Versionado */}
      {dims.versionado && (
        <SectionCard title="Criterios de Versionado">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 14 }}>
            <FieldRow label="Mínimo de commits">
              <Input type="number" value={commitsMin} onChange={e => setCommitsMin(+e.target.value)} />
            </FieldRow>
            <FieldRow label="Mínimo de ramas">
              <Input type="number" value={ramasMin} onChange={e => setRamasMin(+e.target.value)} />
            </FieldRow>
            <FieldRow label="% mínimo de mensajes descriptivos">
              <Input type="number" min={0} max={100} value={qualityUmbral}
                onChange={e => setQualityUmbral(+e.target.value)} />
            </FieldRow>
          </div>
          <FieldRow label="Patrones de mensajes considerados «genéricos»">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
              {generic.map(g => (
                <Tag key={g} label={g} onRemove={() => setGeneric(p => p.filter(x => x !== g))} />
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input placeholder="ej. hotfix" value={newGeneric}
                onChange={e => setNewGeneric(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && newGeneric.trim()) { setGeneric(p => [...p, newGeneric.trim()]); setNewGeneric('') }}}
                style={{ flex: 1 }}
              />
              <Btn variant="secondary" onClick={() => { if (newGeneric.trim()) { setGeneric(p => [...p, newGeneric.trim()]); setNewGeneric('') }}}>
                + Agregar
              </Btn>
            </div>
          </FieldRow>
        </SectionCard>
      )}

      {/* Criterios Temporales */}
      {dims.temporal && (
        <SectionCard title="Criterios Temporales">
          <FieldRow label="Fecha límite (UTC)">
            <Input type="datetime-local" value={deadline} onChange={e => setDeadline(e.target.value)} style={{ width: 220 }} />
          </FieldRow>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 14 }}>
            <FieldRow label="Inicio período académico">
              <Input type="date" value={periodStart} onChange={e => setPeriodStart(e.target.value)} />
            </FieldRow>
            <FieldRow label="Fin período académico">
              <Input type="date" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)} />
            </FieldRow>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
            <FieldRow label="Intervalo de actividad mínima">
              <select value={interval} onChange={e => setInterval(e.target.value)}
                style={{ width: '100%', padding: '8px 10px', borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 13 }}>
                <option value="semana">Semana</option>
                <option value="quincena">Quincena</option>
                <option value="mes">Mes</option>
              </select>
            </FieldRow>
            <FieldRow label="Umbral concentración final (%)">
              <Input type="number" value={concUmbral} onChange={e => setConcUmbral(+e.target.value)} />
            </FieldRow>
            <FieldRow label="N días para concentración">
              <Input type="number" value={concDias} onChange={e => setConcDias(+e.target.value)} />
            </FieldRow>
          </div>
        </SectionCard>
      )}

      {/* Criterios de Contenido */}
      {dims.contenido && (
        <SectionCard title="Criterios de Contenido">
          <FieldRow label="Requisitos funcionales que Claude verificará en el código">
            {contenido.requisitos.length === 0 && (
              <div style={{ fontSize: 12, color: C.amber, marginBottom: 8 }}>
                Sin requisitos: el agente de contenido no tendrá nada que verificar.
              </div>
            )}
            {contenido.requisitos.map((r, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0',
                borderBottom: `1px solid ${C.border}`,
              }}>
                <span style={{ fontSize: 12, color: C.textSub, width: 18 }}>{i + 1}.</span>
                <span style={{ flex: 1, fontSize: 13 }}>{r.texto}</span>
                <Input type="number" min={0} max={weights.contenido}
                  placeholder="auto"
                  value={r.peso_pct ?? ''}
                  onChange={e => setRequisitoPeso(i, e.target.value)}
                  style={{ width: 70, textAlign: 'right' }} />
                <span style={{ fontSize: 12, color: C.textSub }}>pts</span>
                <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px', color: C.red }}
                  onClick={() => setContenido(p => ({ ...p, requisitos: p.requisitos.filter((_, idx) => idx !== i) }))}>
                  Quitar
                </Btn>
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <Input placeholder="ej. Usar estructuras condicionales (if/else) para validar entradas"
                value={newRequisito}
                onChange={e => setNewRequisito(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addRequisito() }}
                style={{ flex: 1 }}
              />
              <Btn variant="secondary" onClick={addRequisito}>+ Agregar</Btn>
            </div>
            <div style={{ fontSize: 12, marginTop: 6, color: pesoAsignadoContenido > weights.contenido ? C.red : C.textSub }}>
              Redacta cada requisito de forma clara y verificable. Déjalo en "auto" para repartir en
              partes iguales los puntos que le queden a Contenido, o asígnale puntos puntuales
              (ej. si Contenido vale {weights.contenido}, "usa condicionales" puede valer 10).
              Esto también cuenta lo que hayas asignado en "Requisitos de contenido en una rama
              específica", más abajo — todos comparten el mismo presupuesto.
              {pesoAsignadoContenido > 0 && ` Asignado a mano: ${pesoAsignadoContenido.toFixed(1)} de ${weights.contenido} pts.`}
              {pesoAsignadoContenido > weights.contenido && ' Supera el peso de Contenido, se reescalará automáticamente.'}
            </div>
          </FieldRow>

          <FieldRow label="Requisitos de contenido en una rama específica (ej. README con los prompts usados)">
            {requisitosPorRama.map((g, gi) => (
              <div key={gi} style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>
                    Rama <code>{g.rama}</code> — archivos: {g.archivos.join(', ')}
                  </span>
                  <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px', color: C.red }}
                    onClick={() => setRequisitosPorRama(p => p.filter((_, idx) => idx !== gi))}>
                    Quitar rama
                  </Btn>
                </div>
                {g.requisitos.map((r, ri) => (
                  <div key={ri} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                    <span style={{ flex: 1, fontSize: 13 }}>{r.texto}</span>
                    <Input type="number" min={0} max={weights.contenido} placeholder="auto"
                      value={r.peso_pct ?? ''}
                      onChange={e => setRequisitoGrupoPeso(gi, ri, e.target.value)}
                      style={{ width: 70, textAlign: 'right' }} />
                    <span style={{ fontSize: 12, color: C.textSub }}>pts</span>
                    <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px', color: C.red }}
                      onClick={() => setRequisitosPorRama(p => p.map((x, idx) => idx !== gi ? x : {
                        ...x, requisitos: x.requisitos.filter((_, idx2) => idx2 !== ri),
                      }))}>
                      Quitar
                    </Btn>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                  <Input placeholder="ej. El README documenta los prompts usados para generar el proyecto"
                    value={newGrupoReqTexto[gi] || ''}
                    onChange={e => setNewGrupoReqTexto(p => ({ ...p, [gi]: e.target.value }))}
                    onKeyDown={e => { if (e.key === 'Enter') addRequisitoGrupo(gi) }}
                    style={{ flex: 1 }} />
                  <Btn variant="secondary" onClick={() => addRequisitoGrupo(gi)}>+ Agregar requisito</Btn>
                </div>
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <Input placeholder="rama (ej. prompts)" value={newGrupoRama}
                onChange={e => setNewGrupoRama(e.target.value)} style={{ width: 160 }} />
              <Input placeholder="archivos a leer, separados por coma (ej. README.md)"
                value={newGrupoArchivos} onChange={e => setNewGrupoArchivos(e.target.value)}
                style={{ flex: 1 }} />
              <Btn variant="secondary" onClick={addGrupoRama}>+ Agregar rama</Btn>
            </div>
          </FieldRow>
          <FieldRow label="Extensiones de archivo a analizar">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
              {contenido.extensiones.map(e => (
                <Tag key={e} label={e}
                  onRemove={() => setContenido(p => ({ ...p, extensiones: p.extensiones.filter(x => x !== e) }))} />
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input placeholder="ej. .go" value={newExt}
                onChange={e => setNewExt(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addExt() }}
                style={{ flex: 1 }}
              />
              <Btn variant="secondary" onClick={addExt}>+ Agregar</Btn>
            </div>
          </FieldRow>
          <FieldRow label="Máximo de archivos por repositorio">
            <Input type="number" min={1} value={contenido.maxArchivos}
              onChange={e => setContenido(p => ({ ...p, maxArchivos: Math.max(1, +e.target.value) }))}
              style={{ width: 160 }} />
          </FieldRow>
        </SectionCard>
      )}

      {/* Guardar configuración */}
      <SectionCard title="Guardar configuración">
        <FieldRow label="Nombre de la configuración">
          <div style={{ display: 'flex', gap: 8 }}>
            <Input placeholder="ej. Proyecto Final – Bases de Datos"
              value={configName} onChange={e => setConfigName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') saveConfig() }}
              style={{ flex: 1 }}
            />
            <Btn onClick={saveConfig} disabled={!configName.trim()}>Guardar configuración</Btn>
          </div>
        </FieldRow>

        <FieldRow label="Reutilizar entre asignaturas y ciclos (archivo YAML)">
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn variant="secondary" onClick={exportYAML}>Exportar YAML</Btn>
            <Btn variant="secondary" onClick={() => yamlInputRef.current?.click()}>Importar YAML</Btn>
            <input ref={yamlInputRef} type="file" accept=".yaml,.yml" style={{ display: 'none' }} onChange={importYAML} />
          </div>
          <div style={{ fontSize: 12, color: C.textSub, marginTop: 6 }}>
            El archivo exportado tiene el mismo formato que <code>config/default.yaml</code>: puedes
            editarlo a mano, compartirlo con otro docente o usarlo directo con <code>demo.py --criteria</code>.
          </div>
          {importError && (
            <div style={{ fontSize: 12, color: C.red, marginTop: 6 }}>{importError}</div>
          )}
        </FieldRow>

        {savedConfigs.length > 0 && (
          <div>
            <div style={{ fontSize: 12, color: C.textSub, marginBottom: 8 }}>Configuraciones guardadas</div>
            {savedConfigs.map(c => (
              <div key={c.name} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 0', borderBottom: `1px solid ${C.border}`,
              }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{c.name}</div>
                  <div style={{ fontSize: 12, color: C.textSub }}>Actualizado {c.date}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px' }} onClick={() => loadConfig(c)}>Cargar</Btn>
                  <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px' }}
                    onClick={() => { setConfigName(c.name + ' (copia)'); loadConfig(c) }}>Duplicar</Btn>
                  <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px', color: C.red }}
                    onClick={() => deleteConfig(c.name)}>Eliminar</Btn>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      {showWeightsModal && (
        <WeightsModal weights={weights} onChange={setWeights} onClose={() => setShowWeightsModal(false)} />
      )}
    </div>
  )
}

// ─── Vista: Cargar Repositorios ───────────────────────────────────────────────
function CargaView({ onStart, errorMsg }) {
  const [urls, setUrls]       = useState('')
  const [token, setToken]     = useState('')
  const [config, setConfig]   = useState('Configuración por defecto UTPL')
  const [dragging, setDragging] = useState(false)
  const [csvFile, setCsvFile]   = useState(null)
  const dropRef = useRef()

  const repoList = urls.split('\n').filter(u => u.trim().startsWith('http'))

  const handleDrop = useCallback(e => {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files[0]
    if (!file) return
    setCsvFile(file)
    const reader = new FileReader()
    reader.onload = ev => {
      const lines = ev.target.result.split('\n')
        .map(l => l.trim())
        .filter(l => l.startsWith('http'))
      setUrls(lines.join('\n'))
    }
    reader.readAsText(file)
  }, [])

  const handleFileInput = e => {
    const file = e.target.files[0]
    if (!file) return
    setCsvFile(file)
    const reader = new FileReader()
    reader.onload = ev => {
      const lines = ev.target.result.split('\n').map(l => l.trim()).filter(l => l.startsWith('http'))
      setUrls(lines.join('\n'))
    }
    reader.readAsText(file)
  }

  const savedConfigs = (() => {
    try { return JSON.parse(localStorage.getItem('evalrepo_configs') || '[]').map(c => c.name) }
    catch { return [] }
  })()

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: '24px 24px 48px' }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 4px' }}>Cargar Repositorios</h2>
      <p style={{ fontSize: 13, color: C.textSub, margin: '0 0 24px' }}>
        Sube el listado de repositorios de GitHub que el sistema multi-agente evaluará en lote.
      </p>

      {errorMsg && (
        <div style={{
          padding: '10px 14px', marginBottom: 16, borderRadius: 8, fontSize: 13,
          background: C.redSoft, color: C.red, border: `1px solid ${C.redBdr}`,
        }}>
          {errorMsg}
        </div>
      )}

      {/* Dropzone */}
      <SectionCard title="Repositorios a evaluar">
        <div
          ref={dropRef}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => document.getElementById('csv-input').click()}
          style={{
            border: `2px dashed ${dragging ? C.blue : C.border}`,
            borderRadius: 10, padding: '32px 24px', textAlign: 'center',
            background: dragging ? C.blueSoft : C.grayLight,
            cursor: 'pointer', marginBottom: 16, transition: 'all 0.15s',
          }}>
          <input id="csv-input" type="file" accept=".csv,.txt" style={{ display: 'none' }} onChange={handleFileInput} />
          {csvFile ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px', background: C.greenSoft, borderRadius: 8, border: `1px solid ${C.greenBdr}` }}
              onClick={e => e.stopPropagation()}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{csvFile.name}</div>
                  <div style={{ fontSize: 12, color: C.textSub }}>{repoList.length} URLs detectadas · {(csvFile.size/1024).toFixed(1)} kB</div>
                </div>
              </div>
              <Btn variant="ghost" style={{ color: C.red, fontSize: 12 }}
                onClick={() => { setCsvFile(null); setUrls('') }}>Quitar archivo</Btn>
            </div>
          ) : (
            <>
              <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>
                {dragging ? 'Suelta el archivo para cargarlo' : 'Arrastra un archivo CSV aquí o haz clic para seleccionar'}
              </div>
              <div style={{ fontSize: 12, color: C.textSub }}>
                Formato: una URL de repositorio por línea, o columna «url» en CSV
              </div>
            </>
          )}
        </div>

        <div style={{ textAlign: 'center', fontSize: 12, color: C.textSub, margin: '8px 0' }}>
          — o pega las URLs directamente —
        </div>

        <textarea
          value={urls}
          onChange={e => { setUrls(e.target.value); setCsvFile(null) }}
          placeholder="https://github.com/estudiante/proyecto-final&#10;https://github.com/estudiante2/proyecto-final"
          style={{
            width: '100%', height: 110, padding: '10px 12px',
            border: `1px solid ${C.border}`, borderRadius: 8,
            fontFamily: 'monospace', fontSize: 12, lineHeight: 1.8,
            resize: 'vertical', boxSizing: 'border-box', outline: 'none',
          }}
        />
      </SectionCard>

      {/* Credenciales */}
      <SectionCard title="Credenciales y configuración">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <FieldRow label="Token de acceso GitHub">
            <Input type="password" value={token} onChange={e => setToken(e.target.value)}
              placeholder="ghp_..." />
            <div style={{ fontSize: 11, color: C.textSub, marginTop: 4 }}>
              El token no se almacena en texto plano; se usa solo durante la ejecución.
            </div>
          </FieldRow>
          <FieldRow label="Configuración de criterios a aplicar">
            <select value={config} onChange={e => setConfig(e.target.value)}
              style={{ width: '100%', padding: '8px 10px', borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 13 }}>
              <option>Configuración por defecto UTPL</option>
              {savedConfigs.map(n => <option key={n}>{n}</option>)}
            </select>
          </FieldRow>
        </div>
      </SectionCard>

      {/* Preview */}
      {repoList.length > 0 && (
        <SectionCard title={`Vista previa de repositorios detectados`}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, color: C.textSub }}>{repoList.length} repositorios</span>
            <Badge type="ok">{repoList.length} válidos</Badge>
          </div>
          {repoList.slice(0, 5).map((url, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '7px 10px', borderRadius: 6, marginBottom: 4,
              background: C.grayLight, fontSize: 13,
            }}>
              <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
                {url.replace('https://github.com/', '')}
              </span>
              <Badge type="ok" style={{ fontSize: 11 }}>válido</Badge>
            </div>
          ))}
          {repoList.length > 5 && (
            <div style={{ fontSize: 12, color: C.textSub, textAlign: 'center', marginTop: 6 }}>
              y {repoList.length - 5} repositorios más
            </div>
          )}
        </SectionCard>
      )}

      {/* Acciones */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Btn variant="secondary" onClick={() => { setUrls(''); setCsvFile(null); setToken('') }}>Cancelar</Btn>
        <Btn
          disabled={!token || repoList.length === 0}
          onClick={() => onStart(repoList, token, config)}>
          Iniciar evaluación
        </Btn>
      </div>
    </div>
  )
}

// ─── Vista: Ejecución ─────────────────────────────────────────────────────────
function EjecucionView({ evalId, status, processed, total, repoList, results, onViewReport, setTab, errorMsg, warningMsg }) {
  const agentStatus = useCallback(() => {
    if (!status || status === 'idle') return null
    const pct = total > 0 ? (processed / total) * 100 : 0
    if (status === 'done') return { coord: 'listo', extrac: 'listo', struct: 'listo', version: 'listo', content: 'listo' }
    if (pct < 15)  return { coord: 'activo',   extrac: 'activo',  struct: 'pendiente', version: 'pendiente', content: 'pendiente' }
    if (pct < 40)  return { coord: 'activo',   extrac: 'listo',   struct: 'activo',    version: 'activo',    content: 'pendiente' }
    if (pct < 70)  return { coord: 'activo',   extrac: 'listo',   struct: 'listo',     version: 'activo',    content: 'activo'    }
    return            { coord: 'activo',   extrac: 'listo',   struct: 'listo',     version: 'listo',     content: 'activo'    }
  }, [status, processed, total])

  const ag = agentStatus()
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0

  const agentLabels = [
    { key: 'coord',   label: 'Coordinador' },
    { key: 'extrac',  label: 'Extracción'  },
    { key: 'struct',  label: 'Estructural' },
    { key: 'version', label: 'Versionado'  },
    { key: 'content', label: 'Contenido'   },
  ]

  const getRepoStatus = (url, i) => {
    if (status === 'done') return 'completado'
    if (i < processed) return 'completado'
    if (i === processed) return 'procesando'
    return 'pendiente'
  }

  if (!status || status === 'idle') return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 24px', textAlign: 'center' }}>
      <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 8px' }}>Aún no hay evaluaciones</h3>
      <p style={{ fontSize: 13, color: C.textSub, margin: '0 0 20px' }}>
        Carga una lista de repositorios y ejecuta tu primera evaluación para ver reportes aquí.
      </p>
      <Btn onClick={() => setTab('cargar')}>Cargar repositorios</Btn>
    </div>
  )

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: '24px 24px 48px' }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 4px' }}>Ejecución de la Evaluación</h2>
      <p style={{ fontSize: 13, color: C.textSub, margin: '0 0 24px' }}>
        El sistema multi-agente está procesando los repositorios cargados.
      </p>

      {status === 'error' && errorMsg && (
        <div style={{
          padding: '12px 16px', marginBottom: 16, borderRadius: 8, fontSize: 13,
          background: C.redSoft, color: C.red, border: `1px solid ${C.redBdr}`,
        }}>
          <strong>La evaluación se detuvo:</strong> {errorMsg}
        </div>
      )}

      {status === 'running' && warningMsg && (
        <div style={{
          padding: '12px 16px', marginBottom: 16, borderRadius: 8, fontSize: 13,
          background: C.amberSoft, color: C.amber, border: `1px solid ${C.amberBdr}`,
        }}>
          {warningMsg}
        </div>
      )}

      <SectionCard title={`Progreso global — ${processed} de ${total} repositorios procesados`}>
        <div style={{ height: 8, background: C.grayLight, borderRadius: 999, marginBottom: 16 }}>
          <div style={{
            height: '100%', width: `${pct}%`, borderRadius: 999,
            background: status === 'done' ? C.green : C.blue,
            transition: 'width 0.5s ease',
          }} />
        </div>

        {ag && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {agentLabels.map(({ key, label }) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <span style={{ color: C.textSub }}>{label}:</span>
                <Badge type={ag[key]}>
                  {ag[key] === 'activo' ? 'Activo' : ag[key] === 'listo' ? 'Listo' : 'Pendiente'}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Estado por repositorio">
        {repoList.slice(0, 8).map((url, i) => {
          const repoStatus = getRepoStatus(url, i)
          const name = url.replace('https://github.com/', '')
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 0', borderBottom: `1px solid ${C.border}`, gap: 12,
            }}>
              <span style={{ fontFamily: 'monospace', fontSize: 13, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {name}
              </span>
              <Badge type={repoStatus}>
                {repoStatus === 'completado' ? 'Completado' : repoStatus === 'procesando' ? 'Procesando' : 'Pendiente'}
              </Badge>
            </div>
          )
        })}
        {repoList.length > 8 && (
          <div style={{ fontSize: 12, color: C.textSub, textAlign: 'center', padding: '8px 0' }}>
            y {repoList.length - 8} repositorios más
          </div>
        )}
      </SectionCard>

      {status === 'done' && (
        <Btn onClick={() => setTab('reportes')} style={{ width: '100%', justifyContent: 'center', padding: '12px' }}>
          Ver reporte consolidado
        </Btn>
      )}
      {status === 'error' && (
        <Btn variant="secondary" onClick={() => setTab('cargar')} style={{ width: '100%', justifyContent: 'center', padding: '12px' }}>
          Volver a cargar repositorios
        </Btn>
      )}
    </div>
  )
}

// ─── Reporte Individual ───────────────────────────────────────────────────────
function ReporteIndividual({ r, evalId, onBack, onOverride, onOverrideContent }) {
  const [open, setOpen] = useState({ struct: true, version: true, temporal: false, content: false })
  const toggle = k => setOpen(p => ({...p, [k]: !p[k]}))
  const [editingScore, setEditingScore] = useState(false)
  const [scoreInput, setScoreInput] = useState(r.score)
  const [noteInput, setNoteInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  const saveOverride = async () => {
    const val = +scoreInput
    if (Number.isNaN(val) || val < 0 || val > 100) {
      setSaveError('El puntaje debe estar entre 0 y 100.')
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      await onOverride(r.student, r.repo, val, noteInput.trim() || null)
      setEditingScore(false)
    } catch (e) {
      setSaveError(e.message || 'No se pudo guardar el ajuste.')
    } finally {
      setSaving(false)
    }
  }

  // Ajuste por requisito de Contenido: peso (%) + % cumplido por cada requisito,
  // en vez de un único número a ciegas para toda la dimensión.
  const buildDefaultReqRows = () => {
    if (r.content.requirementScores) {
      return r.content.requirementScores.map(rs => ({
        requirement: rs.requirement, weight_pct: rs.weight_pct, achieved_pct: rs.achieved_pct,
      }))
    }
    const all = [
      ...r.content.found.map(req => ({ requirement: req, achieved_pct: 100 })),
      ...r.content.missing.map(req => ({ requirement: req, achieved_pct: 0 })),
    ]
    // si el docente ya les asignó un peso al configurar los criterios, parte de ahí
    // en vez de repartir todo en partes iguales
    const pesos = r.content.requisitosPesos
    const evenWeight = all.length > 0 ? +(r.content.max / all.length).toFixed(2) : 0
    return all.map(x => ({ ...x, weight_pct: pesos?.[x.requirement] ?? evenWeight }))
  }
  const [editingContent, setEditingContent] = useState(false)
  const [reqRows, setReqRows] = useState(buildDefaultReqRows)
  const [contentNote, setContentNote] = useState('')
  const [contentSaving, setContentSaving] = useState(false)
  const [contentError, setContentError] = useState('')
  const totalWeight = reqRows.reduce((a, b) => a + (+b.weight_pct || 0), 0)

  const setReqRow = (i, field, value) => setReqRows(p => p.map((x, idx) => idx === i ? { ...x, [field]: value } : x))

  const saveContentOverride = async () => {
    if (totalWeight > r.content.max + 0.01) {
      setContentError(`Los pesos suman ${totalWeight.toFixed(1)}, pero Contenido vale ${r.content.max} puntos — no pueden sumar más que eso.`)
      return
    }
    setContentSaving(true)
    setContentError('')
    try {
      await onOverrideContent(r.student, r.repo, reqRows.map(x => ({
        requirement: x.requirement, weight_pct: +x.weight_pct || 0, achieved_pct: +x.achieved_pct || 0,
      })), contentNote.trim() || null)
      setEditingContent(false)
    } catch (e) {
      setContentError(e.message || 'No se pudo guardar el ajuste.')
    } finally {
      setContentSaving(false)
    }
  }

  const Section = ({ id, label, score, max, status, children }) => (
    <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 12, overflow: 'hidden' }}>
      <button onClick={() => toggle(id)} style={{
        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 20px', border: 'none', background: 'none', cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{label}</span>
          <Badge type={status === 'ok' ? 'ok' : status === 'alerta' ? 'alerta' : 'falla'}>
            {status === 'ok' ? 'Cumple' : status === 'alerta' ? 'Alerta' : 'No cumple'}
          </Badge>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: scoreColor(Math.round((score/max)*100)) }}>
            {Math.round(score)}/{Math.round(max)}
          </span>
          <span style={{ color: C.textSub, fontSize: 12 }}>{open[id] ? 'ocultar' : 'ver más'}</span>
        </div>
      </button>
      {open[id] && <div style={{ padding: '0 20px 16px' }}>{children}</div>}
    </div>
  )

  const Bullet = ({ text, ok }) => (
    <div style={{ display: 'flex', gap: 8, marginBottom: 6, fontSize: 13 }}>
      <span style={{ color: ok ? C.green : C.red, flexShrink: 0 }}>·</span>
      <span style={{ color: C.text }}>{text}</span>
    </div>
  )

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: '24px 24px 48px' }}>
      <button onClick={onBack} style={{
        display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
        color: C.textSub, background: 'none', border: 'none', cursor: 'pointer', marginBottom: 20, padding: 0,
      }}>Volver al consolidado</button>

      {/* Header */}
      <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, padding: '20px 24px', marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h2 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 600 }}>
              {r.student} / <code style={{ fontFamily: 'monospace' }}>{r.repo}</code>
            </h2>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <Badge type={r.status === 'ok' ? 'ok' : r.status === 'alerta' ? 'alerta' : 'falla'}>
                {r.pattern}
              </Badge>
              <Badge type={r.onTime ? 'ok' : 'falla'}>
                {r.onTime ? 'Entregado a tiempo' : 'Entregado tarde'}
              </Badge>
            </div>
            <div style={{ fontSize: 12, color: C.textSub }}>
              {r.commits} commits · {r.branches} ramas · {r.quality}% mensajes descriptivos
            </div>
          </div>
          <div style={{ textAlign: 'center', minWidth: 160 }}>
            <div style={{ fontSize: 36, fontWeight: 700, color: scoreColor(r.score), lineHeight: 1 }}>{r.score}</div>
            <div style={{ fontSize: 13, color: C.textSub }}>/ 100 puntos</div>
            {r.scoreOverridden && (
              <div style={{ fontSize: 11, color: C.blue, marginTop: 4 }}>
                Ajustado manualmente (calculado: {r.originalScore})
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'center' }}>
              <Btn variant="secondary" style={{ fontSize: 12, padding: '5px 12px' }}
                onClick={() => evalId && window.open(`${API_BASE}/reports/${evalId}/${r.student}/${r.repo}`, '_blank')}>
                Exportar reporte
              </Btn>
              {onOverride && (
                <Btn variant="ghost" style={{ fontSize: 12, padding: '5px 8px' }}
                  onClick={() => { setEditingScore(v => !v); setScoreInput(r.score); setNoteInput(r.overrideNote || ''); setSaveError('') }}>
                  Ajustar puntaje
                </Btn>
              )}
            </div>
          </div>
        </div>

        {editingScore && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
            <div style={{ fontSize: 12, color: C.textSub, marginBottom: 8 }}>
              Modificar el puntaje total de este repositorio. Queda registrado el puntaje que calculó
              el sistema ({r.score}) junto con la justificación que escribas.
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <Input type="number" min={0} max={100} value={scoreInput}
                onChange={e => setScoreInput(e.target.value)}
                style={{ width: 90 }} />
              <Input placeholder="Justificación (opcional)" value={noteInput}
                onChange={e => setNoteInput(e.target.value)}
                style={{ flex: 1, minWidth: 220 }} />
              <Btn onClick={saveOverride} disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</Btn>
              <Btn variant="secondary" onClick={() => setEditingScore(false)}>Cancelar</Btn>
            </div>
            {saveError && <div style={{ color: C.red, fontSize: 12, marginTop: 6 }}>{saveError}</div>}
          </div>
        )}
      </div>

      {/* Secciones */}
      <Section id="struct" label="Estructural" score={r.struct.score} max={r.struct.max}
        status={r.struct.ok ? 'ok' : 'falla'}>
        {Object.entries(r.struct.files).map(([f, present]) => (
          <Bullet key={f} ok={present} text={present ? `${f} presente` : `${f} ausente`} />
        ))}
        <Bullet ok={r.struct.readmeOk} text={`README: ${r.struct.readmeChars} caracteres`} />
        {r.struct.branchChecks.map((c, i) => (
          <Bullet key={`branch-${i}`} ok={c.found}
            text={`${c.path} en rama "${c.branch}"${c.found ? ' presente' : ' ausente'}`} />
        ))}
        {r.struct.alternativeChecks.map((c, i) => (
          <Bullet key={`alt-${i}`} ok={c.found}
            text={c.found ? `${c.nombre} encontrado en ${c.found_in}` : `${c.nombre} no encontrado en ${c.carpetas.join(' ó ')}`} />
        ))}
      </Section>

      <Section id="version" label="Versionado" score={r.versioning.score} max={r.versioning.max}
        status={r.versioning.ok ? 'ok' : r.versioning.commitsOk ? 'alerta' : 'falla'}>
        <Bullet ok={r.versioning.commitsOk} text={`${r.commits} commits (mínimo: ${r.versioning.commitsMin})`} />
        <Bullet ok={r.versioning.qualityOk} text={`${r.quality}% de mensajes descriptivos (umbral: ${r.versioning.qualityUmbral}%)`} />
        {r.genericMessages.length > 0 && (
          <Bullet ok={false} text={`Mensajes genéricos detectados: "${r.genericMessages.slice(0,3).join('", "')}"`} />
        )}
        <Bullet ok={r.versioning.branchesOk} text={`${r.branches} ramas activas (mínimo: ${r.versioning.ramasMin})`} />
      </Section>

      <Section id="temporal" label="Temporal" score={r.temporal.score} max={r.temporal.max}
        status={r.temporal.ok ? 'ok' : r.temporal.concentrationAlert ? 'falla' : 'alerta'}>
        <Bullet ok={r.onTime} text={r.onTime ? 'Entregado antes de la fecha límite' : 'Entregado después de la fecha límite'} />
        <Bullet ok={r.temporal.activityOk} text={`Actividad en ${r.temporal.activeWeeks} de ${r.temporal.totalWeeks} semanas del período`} />
        {r.temporal.concentrationAlert && (
          <Bullet ok={false} text={`${r.temporal.concentrationPct}% de commits concentrados al final del período`} />
        )}
      </Section>

      <Section id="content" label="Contenido" score={r.content.score} max={r.content.max}
        status={r.content.coherence === 'Alta' ? 'ok' : r.content.coherence === 'Media' ? 'alerta' : 'falla'}>
        {r.content.requirementScores ? (
          r.content.requirementScores.map((rs, i) => (
            <Bullet key={i} ok={rs.achieved_pct >= 100}
              text={`${rs.requirement} — vale ${rs.weight_pct} pts, ${rs.achieved_pct}% cumplido (${rs.points} pts obtenidos)`} />
          ))
        ) : (
          <>
            {r.content.found.map(req => (
              <Bullet key={req} ok text={r.content.requisitosPesos?.[req] ? `${req} (${r.content.requisitosPesos[req].toFixed(1)} pts)` : req} />
            ))}
            {r.content.missing.map(req => (
              <Bullet key={req} ok={false} text={r.content.requisitosPesos?.[req] ? `${req} (${r.content.requisitosPesos[req].toFixed(1)} pts)` : req} />
            ))}
          </>
        )}
        {r.content.branchRequirements.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 12, color: C.textSub, marginBottom: 6 }}>Requisitos verificados en ramas específicas:</div>
            {r.content.branchRequirements.map((br, i) => (
              <div key={i} style={{ background: C.grayLight, borderRadius: 8, padding: '8px 12px', marginBottom: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                  Rama <code>{br.branch}</code>
                  {br.archivos_analizados?.length > 0 && <span style={{ color: C.textSub, fontWeight: 400 }}> — {br.archivos_analizados.join(', ')}</span>}
                </div>
                {br.requirements_found.map(req => <Bullet key={req} ok text={req} />)}
                {br.requirements_missing.map(req => <Bullet key={req} ok={false} text={req} />)}
                {br.summary && <div style={{ fontSize: 12, color: C.textSub, marginTop: 4 }}>{br.summary}</div>}
              </div>
            ))}
          </div>
        )}
        {r.content.summary && (
          <div style={{ marginTop: 10, padding: '10px 14px', background: C.grayLight, borderRadius: 8, fontSize: 13, lineHeight: 1.7, color: C.text }}>
            {r.content.summary}
          </div>
        )}
        {onOverrideContent && (
          <div style={{ marginTop: 12 }}>
            {!editingContent ? (
              <Btn variant="ghost" style={{ fontSize: 12, padding: '3px 8px' }}
                onClick={() => { setReqRows(buildDefaultReqRows()); setContentNote(''); setContentError(''); setEditingContent(true) }}>
                Ajustar por requisito
              </Btn>
            ) : (
              <div style={{ paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 12, color: C.textSub, marginBottom: 8 }}>
                  Asigna cuántos puntos (de los {r.content.max} que vale Contenido) vale cada
                  requisito, y qué % de ese requisito cumplió. Los puntos no pueden sumar más que
                  el total de Contenido.
                </div>
                {reqRows.map((row, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0' }}>
                    <span style={{ flex: 1, fontSize: 13 }}>{row.requirement}</span>
                    <Input type="number" min={0} max={r.content.max} value={row.weight_pct}
                      onChange={e => setReqRow(i, 'weight_pct', e.target.value)}
                      style={{ width: 70 }} />
                    <span style={{ fontSize: 12, color: C.textSub }}>pts</span>
                    <Input type="number" min={0} max={100} value={row.achieved_pct}
                      onChange={e => setReqRow(i, 'achieved_pct', e.target.value)}
                      style={{ width: 70 }} />
                    <span style={{ fontSize: 12, color: C.textSub }}>% cumplido</span>
                  </div>
                ))}
                <div style={{
                  fontSize: 12, fontWeight: 600, marginTop: 6,
                  color: totalWeight > r.content.max ? C.red : C.textSub,
                }}>
                  Suma de puntos: {totalWeight.toFixed(1)} de {r.content.max}
                  {totalWeight > r.content.max ? ' — supera el total de Contenido' : ''}
                </div>
                <Input placeholder="Justificación (opcional)" value={contentNote}
                  onChange={e => setContentNote(e.target.value)}
                  style={{ marginTop: 8 }} />
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <Btn onClick={saveContentOverride} disabled={contentSaving}>
                    {contentSaving ? 'Guardando…' : 'Guardar'}
                  </Btn>
                  <Btn variant="secondary" onClick={() => setEditingContent(false)}>Cancelar</Btn>
                </div>
                {contentError && <div style={{ color: C.red, fontSize: 12, marginTop: 6 }}>{contentError}</div>}
              </div>
            )}
          </div>
        )}
      </Section>

      {/* Gráfico semanal */}
      {r.weekly.length > 0 && (
        <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px 20px', marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Actividad semanal (commits)</h4>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={r.weekly} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
              <XAxis dataKey="w" tick={{ fontSize: 10 }} interval={0} angle={-35} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip formatter={v => [v, 'Commits']} labelFormatter={(label, items) => items?.[0]?.payload?.range || label} />
              <Bar dataKey="n" radius={[3,3,0,0]}>
                {r.weekly.map((d, i) => (
                  <Cell key={i} fill={d.n === 0 ? '#E2E8F0' : d.n >= 3 ? C.green : C.blue} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 12, color: C.textSub }}>
            <span><span style={{ display: 'inline-block', width: 10, height: 10, background: C.green, borderRadius: 2, marginRight: 4 }} />Semana activa</span>
            <span><span style={{ display: 'inline-block', width: 10, height: 10, background: '#E2E8F0', borderRadius: 2, marginRight: 4 }} />Semana sin actividad</span>
          </div>
        </div>
      )}

      {/* Colaboradores */}
      {r.contributors.length > 0 && (
        <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px 20px', marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Colaboradores</h4>
          {r.contributors.map(c => (
            <div key={c.author} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${C.border}`, fontSize: 13 }}>
              <span>{c.author}</span>
              <span style={{ fontWeight: 600 }}>{c.commits} commit{c.commits !== 1 ? 's' : ''}</span>
            </div>
          ))}
        </div>
      )}

      {/* Historial de commits */}
      {r.commitLog.length > 0 && (
        <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px 20px', marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Historial de commits</h4>
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: C.textSub, fontSize: 11, textTransform: 'uppercase' }}>
                  <th style={{ padding: '4px 8px', position: 'sticky', top: 0, background: C.white }}>Fecha</th>
                  <th style={{ padding: '4px 8px', position: 'sticky', top: 0, background: C.white }}>Autor</th>
                  <th style={{ padding: '4px 8px', position: 'sticky', top: 0, background: C.white }}>Mensaje</th>
                </tr>
              </thead>
              <tbody>
                {r.commitLog.map((c, i) => (
                  <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ padding: '6px 8px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                      {c.date ? c.date.slice(0, 16).replace('T', ' ') : '—'}
                    </td>
                    <td style={{ padding: '6px 8px' }}>{c.author}</td>
                    <td style={{ padding: '6px 8px' }}>{c.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alertas activas */}
      {r.alerts.length > 0 && (
        <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px 20px', marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Alertas activas</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {r.alerts.map((a, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 12px', background: C.amberSoft, borderRadius: 7, border: `1px solid ${C.amberBdr}` }}>
                <span style={{ fontSize: 13, color: C.text }}>{a}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Observaciones */}
      {r.content.summary && (
        <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 10, padding: '16px 20px' }}>
          <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 600 }}>Observaciones del sistema</h4>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: C.text }}>{r.content.summary}</p>
        </div>
      )}
    </div>
  )
}

// ─── Vista: Reportes ──────────────────────────────────────────────────────────
function ReportesView({ results, evalId, setTab, onOverride, onOverrideContent }) {
  const [selected, setSelected] = useState(null)
  const [filterStatus, setFilterStatus] = useState('todos')
  const [filterAlerts, setFilterAlerts] = useState('todos')
  const [filterUmbral, setFilterUmbral] = useState('todos')
  const [sortBy, setSortBy] = useState('puntaje')

  if (selected) return <ReporteIndividual r={selected} evalId={evalId} onBack={() => setSelected(null)}
    onOverride={onOverride ? async (student, repo, score, note) => {
      const updated = await onOverride(student, repo, score, note)
      setSelected(s => ({ ...s, ...updated }))
    } : null}
    onOverrideContent={onOverrideContent ? async (student, repo, requirements, note) => {
      const updated = await onOverrideContent(student, repo, requirements, note)
      setSelected(s => ({ ...s, ...updated }))
    } : null} />

  if (!results.length) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 24px', textAlign: 'center' }}>
      <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 8px' }}>Aún no hay evaluaciones</h3>
      <p style={{ fontSize: 13, color: C.textSub, margin: '0 0 20px' }}>
        Carga una lista de repositorios y ejecuta tu primera evaluación para ver reportes aquí.
      </p>
      <Btn onClick={() => setTab('cargar')}>Cargar repositorios</Btn>
    </div>
  )

  const aprobMin = 60
  let filtered = results
    .filter(r => filterStatus === 'todos' || r.status === filterStatus)
    .filter(r => filterAlerts === 'todos' || (filterAlerts === 'con' ? r.alerts.length > 0 : r.alerts.length === 0))
    .filter(r => filterUmbral === 'todos' || r.score < aprobMin)
    .sort((a, b) => sortBy === 'puntaje' ? b.score - a.score : a.student.localeCompare(b.student))

  const exportCSV = () => {
    const rows = [
      ['Estudiante', 'Repositorio', 'Puntaje', 'Estructural', 'Versionado', 'Temporal', 'Contenido', 'Patrón', 'Entrega', 'Alertas'],
      ...results.map(r => [
        r.student, r.repo, r.score,
        r.struct.score, r.versioning.score, r.temporal.score, r.content.score,
        r.pattern, r.onTime ? 'A tiempo' : 'Tarde', r.alerts.length,
      ])
    ]
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'evalrepo-resultados.csv'; a.click()
  }

  const DimBadge = ({ score, max }) => {
    const pct = max > 0 ? (score / max) * 100 : 0
    const type = pct >= 70 ? 'ok' : pct >= 50 ? 'alerta' : 'falla'
    return <Badge type={type}>{type === 'ok' ? 'OK' : type === 'alerta' ? 'Alerta' : 'Falla'}</Badge>
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 24px 48px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 4px' }}>Reporte Consolidado</h2>
          <p style={{ fontSize: 13, color: C.textSub, margin: 0 }}>
            {results.length} repositorios evaluados · Umbral mínimo de aprobación: {aprobMin} puntos
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {evalId && (
            <Btn variant="secondary" onClick={() => window.open(`${API_BASE}/reports/${evalId}`, '_blank')}>
              HTML consolidado
            </Btn>
          )}
          <Btn variant="secondary" onClick={exportCSV}>Exportar CSV</Btn>
          {evalId && (
            <Btn variant="secondary" onClick={() => window.open(`${API_BASE}/reports/${evalId}/excel`, '_blank')}>
              Descargar Excel
            </Btn>
          )}
        </div>
      </div>

      {/* Filtros */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <label style={{ fontSize: 12, color: C.textSub, marginRight: 6 }}>Filtrar por cumplimiento</label>
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 13 }}>
            <option value="todos">Todos</option>
            <option value="ok">Aprobados</option>
            <option value="alerta">En riesgo</option>
            <option value="falla">Reprobados</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, color: C.textSub, marginRight: 6 }}>Filtrar por alertas</label>
          <select value={filterAlerts} onChange={e => setFilterAlerts(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 13 }}>
            <option value="todos">Todas</option>
            <option value="con">Con alertas</option>
            <option value="sin">Sin alertas</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, color: C.textSub, marginRight: 6 }}>Umbral mínimo</label>
          <select value={filterUmbral} onChange={e => setFilterUmbral(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 13 }}>
            <option value="todos">Todos</option>
            <option value="bajo">Bajo el umbral ({aprobMin} pts)</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, color: C.textSub, marginRight: 6 }}>Ordenar por</label>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 7, border: `1px solid ${C.border}`, fontSize: 13 }}>
            <option value="puntaje">Puntaje (mayor a menor)</option>
            <option value="nombre">Nombre (A–Z)</option>
          </select>
        </div>
      </div>

      {/* Tabla */}
      <div style={{ background: C.white, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#F8FAFC' }}>
              {['Repositorio', 'Puntaje', 'Estructural', 'Versionado', 'Temporal', 'Contenido', 'Alertas'].map(h => (
                <th key={h} style={{
                  padding: '10px 16px', textAlign: 'left', fontSize: 12, fontWeight: 600,
                  color: C.textSub, borderBottom: `1px solid ${C.border}`,
                  textTransform: 'uppercase', letterSpacing: 0.4,
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={r.id || i} onClick={() => setSelected(r)}
                style={{ borderBottom: `1px solid ${C.border}`, cursor: 'pointer', transition: 'background 0.1s' }}
                onMouseOver={e => e.currentTarget.style.background = '#F8FAFC'}
                onMouseOut={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ padding: '12px 16px' }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{r.student}</div>
                  <div style={{ fontSize: 12, color: C.textSub, fontFamily: 'monospace' }}>{r.repo}</div>
                </td>
                <td style={{ padding: '12px 16px' }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: scoreColor(r.score) }}>{r.score}</span>
                  {r.scoreOverridden && (
                    <span title={`Ajustado manualmente (calculado: ${r.originalScore})`} style={{ marginLeft: 4, color: C.blue, fontSize: 12, cursor: 'help' }}>✎</span>
                  )}
                </td>
                <td style={{ padding: '12px 16px' }}><DimBadge score={r.struct.score} max={r.struct.max} /></td>
                <td style={{ padding: '12px 16px' }}><DimBadge score={r.versioning.score} max={r.versioning.max} /></td>
                <td style={{ padding: '12px 16px' }}><DimBadge score={r.temporal.score} max={r.temporal.max} /></td>
                <td style={{ padding: '12px 16px' }}><DimBadge score={r.content.score} max={r.content.max} /></td>
                <td style={{ padding: '12px 16px' }}>
                  {r.alerts.length > 0
                    ? <span style={{ color: C.amber, fontSize: 13, fontWeight: 500 }}>{r.alerts.length}</span>
                    : <span style={{ color: C.textSub }}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: C.textSub, fontSize: 13 }}>
            No hay repositorios que coincidan con los filtros seleccionados.
          </div>
        )}
      </div>
    </div>
  )
}

// ─── App principal ────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab]             = useState('criterios')
  const [weights, setWeights]     = useState({ estructural: 25, versionado: 40, temporal: 25, contenido: 10 })
  const [contenido, setContenido] = useState(DEFAULT_CONTENIDO)
  // Resto de los criterios configurables (RF-01/RF-02): viven acá, no en CriteriosView,
  // para poder armar el payload completo de `/evaluate` al iniciar una evaluación.
  const [dims, setDims]           = useState({ estructural: true, versionado: true, temporal: true, contenido: true })
  const [files, setFiles]         = useState(DEFAULT_FILES)
  const [readmeMin, setReadmeMin] = useState(500)
  const [commitsMin, setCommitsMin] = useState(10)
  const [ramasMin, setRamasMin]   = useState(2)
  const [qualityUmbral, setQualityUmbral] = useState(DEFAULT_QUALITY_UMBRAL)
  const [generic, setGeneric]     = useState(DEFAULT_GENERIC)
  const [deadline, setDeadline]   = useState('2026-08-31T23:59')
  const [periodStart, setPeriodStart] = useState('2024-08-01')
  const [periodEnd, setPeriodEnd]     = useState('2026-12-31')
  const [concUmbral, setConcUmbral]   = useState(60)
  const [concDias, setConcDias]       = useState(3)
  const [archivosPorRama, setArchivosPorRama] = useState([])
  const [archivosAlternativos, setArchivosAlternativos] = useState([])
  const [requisitosPorRama, setRequisitosPorRama] = useState([])
  const [evalId, setEvalId]       = useState(null)
  const [evalStatus, setEvalStatus] = useState('idle')
  const [evalError, setEvalError] = useState('')
  const [processed, setProcessed] = useState(0)
  const [total, setTotal]         = useState(0)
  const [repoList, setRepoList]   = useState([])
  const [results, setResults]     = useState([])
  const pollRef = useRef(null)
  const pollFailuresRef = useRef(0)
  const pollStartedAtRef = useRef(null)
  const [pollWarning, setPollWarning] = useState('')

  // Polling del estado de evaluación
  useEffect(() => {
    if (!evalId || evalStatus !== 'running') return
    pollFailuresRef.current = 0
    pollStartedAtRef.current = Date.now()
    setPollWarning('')

    pollRef.current = setInterval(async () => {
      try {
        const res  = await fetch(`${API_BASE}/evaluate/${evalId}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        pollFailuresRef.current = 0   // se recuperó, no era una caída real

        setProcessed(data.processed_repos || 0)
        if (data.status === 'done') {
          clearInterval(pollRef.current)
          setEvalStatus('done')
          const rRes = await fetch(`${API_BASE}/evaluate/${evalId}/results`)
          const raw  = await rRes.json()
          setResults(raw.map(normalizeResult))
          setTab('reportes')
        }
        if (data.status === 'error') {
          clearInterval(pollRef.current)
          setEvalStatus('error')
          setEvalError(
            (data.errors && data.errors.length > 0)
              ? data.errors.join(' ')
              : 'La evaluación se detuvo por un error inesperado en el backend.'
          )
        }

        // si lleva más de 10 minutos "corriendo" sin terminar, avisamos sin
        // dejar de intentar — puede ser normal (muchos repos, Claude lento)
        // o puede ser que algo se quedó trabado
        if (data.status === 'running' && Date.now() - pollStartedAtRef.current > 10 * 60 * 1000) {
          setPollWarning(
            'Esto está tardando más de lo normal. Puede ser porque hay muchos repositorios ' +
            'o el análisis de contenido con Claude está lento — seguimos esperando. Si no avanza ' +
            'nunca, revisá los logs del backend.'
          )
        }
      } catch (e) {
        pollFailuresRef.current += 1
        // una sola falla puede ser un corte de red momentáneo; recién avisamos
        // si se repite varias veces seguidas, para no asustar por nada
        if (pollFailuresRef.current >= 4) {
          clearInterval(pollRef.current)
          setEvalStatus('error')
          setEvalError(
            `Se perdió la conexión con el backend (${API_BASE}). Verificá que siga corriendo ` +
            'y volvé a intentar la evaluación.'
          )
        }
      }
    }, 2500)
    return () => clearInterval(pollRef.current)
  }, [evalId, evalStatus])

  // Ajuste manual del puntaje total de un repositorio desde la interfaz.
  const handleOverride = async (student, repo, score, note) => {
    const res = await fetch(
      `${API_BASE}/evaluate/${evalId}/results/${encodeURIComponent(student)}/${encodeURIComponent(repo)}/score`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ score, note }),
      },
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'No se pudo guardar el ajuste.')
    setResults(prev => prev.map(r => (r.student === student && r.repo === repo)
      ? { ...r, score: data.global_score, scoreOverridden: true, originalScore: data.original_score, overrideNote: data.override_note }
      : r
    ))
    return { score: data.global_score, scoreOverridden: true, originalScore: data.original_score, overrideNote: data.override_note }
  }

  // Ajuste por requisito de Contenido: el docente le asigna un peso (%) y un
  // % de cumplimiento a cada requisito, en vez de cambiar el puntaje a ciegas.
  const handleContentOverride = async (student, repo, requirements, note) => {
    const res = await fetch(
      `${API_BASE}/evaluate/${evalId}/results/${encodeURIComponent(student)}/${encodeURIComponent(repo)}/content-score`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requirements, note }),
      },
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'No se pudo guardar el ajuste.')
    const patch = {
      score: data.global_score, scoreOverridden: true,
      originalScore: data.original_score, overrideNote: data.override_note,
      content: {
        score: data.content.score, max: data.content.max_score,
        coherence: data.content.coherence_level, summary: data.content.llm_summary,
        found: data.content.requirements_found, missing: data.content.requirements_missing,
        requirementScores: data.content.details?.requirement_scores || null,
        ok: (data.content.coherence_level ?? '') === 'Alta',
      },
    }
    setResults(prev => prev.map(r => (r.student === student && r.repo === repo) ? { ...r, ...patch } : r))
    return patch
  }

  const handleStart = async (urls, token) => {
    setRepoList(urls)
    setTotal(urls.length)
    setProcessed(0)
    setResults([])
    setEvalError('')
    setEvalStatus('running')
    setTab('ejecucion')
    const criteria = buildCriteriaPayload({
      weights, dims, files, readmeMin, commitsMin, ramasMin, qualityUmbral,
      generic, deadline, periodStart, periodEnd, concUmbral, concDias, contenido,
      archivosPorRama, archivosAlternativos, requisitosPorRama,
    })
    try {
      const res  = await fetch(`${API_BASE}/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_urls: urls, github_token: token, criteria }),
      })
      const data = await res.json()
      if (!res.ok) {
        setEvalStatus('error')
        setEvalError(data.detail || 'El backend rechazó la configuración de criterios.')
        setTab('cargar')
        return
      }
      setEvalId(data.evaluation_id)
    } catch (e) {
      setEvalStatus('error')
      setEvalError('No se pudo conectar con el backend (' + API_BASE + ').')
      setTab('cargar')
    }
  }

  const TABS = [
    { id: 'criterios', label: 'Criterios'          },
    { id: 'cargar',    label: 'Cargar repositorios' },
    { id: 'ejecucion', label: 'Ejecución'           },
    { id: 'reportes',  label: 'Reportes'            },
  ]

  return (
    <div style={{ minHeight: '100vh', background: C.grayLight, fontFamily: "'Inter', system-ui, sans-serif", fontSize: 14 }}>
      {/* Navbar */}
      <div style={{ background: C.navy, color: C.white, position: 'sticky', top: 0, zIndex: 100, boxShadow: '0 2px 8px rgba(0,0,0,0.2)' }}>
        <div style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 14, fontWeight: 600, padding: '14px 0' }}>
            SMA · Evaluación de Repositorios UTPL
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: tab === t.id ? C.white : 'rgba(255,255,255,0.55)',
                fontWeight: tab === t.id ? 600 : 400, fontSize: 13, padding: '14px 0',
                borderBottom: tab === t.id ? `2px solid ${C.white}` : '2px solid transparent',
              }}>{t.label}</button>
            ))}
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: evalStatus === 'running' ? '#FBBF24' : evalStatus === 'done' ? '#34D399' : 'rgba(255,255,255,0.3)' }} />
              {evalStatus === 'running' ? `Evaluando… ${processed}/${total}` : evalStatus === 'done' ? `${results.length} repos evaluados` : 'Docente conectado'}
            </div>
          </div>
        </div>
      </div>

      {/* Contenido */}
      <div style={{ minHeight: 'calc(100vh - 49px)' }}>
        {tab === 'criterios'  && <CriteriosView
          weights={weights} setWeights={setWeights} contenido={contenido} setContenido={setContenido}
          dims={dims} setDims={setDims} files={files} setFiles={setFiles}
          readmeMin={readmeMin} setReadmeMin={setReadmeMin}
          commitsMin={commitsMin} setCommitsMin={setCommitsMin}
          ramasMin={ramasMin} setRamasMin={setRamasMin}
          qualityUmbral={qualityUmbral} setQualityUmbral={setQualityUmbral}
          generic={generic} setGeneric={setGeneric}
          deadline={deadline} setDeadline={setDeadline}
          periodStart={periodStart} setPeriodStart={setPeriodStart}
          periodEnd={periodEnd} setPeriodEnd={setPeriodEnd}
          concUmbral={concUmbral} setConcUmbral={setConcUmbral}
          concDias={concDias} setConcDias={setConcDias}
          archivosPorRama={archivosPorRama} setArchivosPorRama={setArchivosPorRama}
          archivosAlternativos={archivosAlternativos} setArchivosAlternativos={setArchivosAlternativos}
          requisitosPorRama={requisitosPorRama} setRequisitosPorRama={setRequisitosPorRama}
        />}
        {tab === 'cargar'     && <CargaView onStart={handleStart} errorMsg={evalError} />}
        {tab === 'ejecucion'  && <EjecucionView evalId={evalId} status={evalStatus} processed={processed} total={total} repoList={repoList} results={results} setTab={setTab} errorMsg={evalError} warningMsg={pollWarning} />}
        {tab === 'reportes'   && <ReportesView results={results} evalId={evalId} setTab={setTab} onOverride={handleOverride} onOverrideContent={handleContentOverride} />}
      </div>
    </div>
  )
}
