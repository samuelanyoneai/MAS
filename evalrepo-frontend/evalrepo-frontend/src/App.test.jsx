import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { isValidEvalId, normalizeResult, WeightsModal, CargaView, ReportesView } from './App'
import App from './App'

// ─── isValidEvalId ──────────────────────────────────────────────────────────
// El backend solo genera ids uuid4; esta validación evita que un valor
// manipulado o inesperado se use para construir URLs de la API.

describe('isValidEvalId', () => {
  it('acepta un uuid4 valido', () => {
    expect(isValidEvalId('123e4567-e89b-12d3-a456-426614174000')).toBe(true)
  })

  it('rechaza valores que no tienen forma de uuid', () => {
    expect(isValidEvalId('../../etc/passwd')).toBe(false)
    expect(isValidEvalId('123')).toBe(false)
    expect(isValidEvalId('')).toBe(false)
  })

  it('rechaza valores que no son string', () => {
    expect(isValidEvalId(null)).toBe(false)
    expect(isValidEvalId(undefined)).toBe(false)
    expect(isValidEvalId(42)).toBe(false)
  })
})

// ─── WeightsModal ───────────────────────────────────────────────────────────

const weights = { estructural: 25, versionado: 40, temporal: 25, contenido: 10 }

describe('WeightsModal', () => {
  it('cierra el modal al hacer click en el fondo (role="presentation")', () => {
    const onClose = vi.fn()
    render(<WeightsModal weights={weights} onChange={vi.fn()} onClose={onClose} />)
    fireEvent.click(screen.getByRole('presentation'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('no cierra el modal al hacer click dentro del panel (role="dialog")', () => {
    const onClose = vi.fn()
    render(<WeightsModal weights={weights} onChange={vi.fn()} onClose={onClose} />)
    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
  })
})

// ─── CargaView (dropzone) ───────────────────────────────────────────────────

describe('CargaView dropzone', () => {
  it('expone el dropzone como un control accesible por teclado', () => {
    render(<CargaView onStart={vi.fn()} errorMsg="" />)
    const dropzone = screen.getByRole('button', {
      name: 'Seleccionar archivo CSV o TXT con las URLs de los repositorios',
    })
    expect(dropzone).toHaveAttribute('tabIndex', '0')
  })

  it('activa el selector de archivo al presionar Enter en el dropzone', () => {
    render(<CargaView onStart={vi.fn()} errorMsg="" />)
    const dropzone = screen.getByRole('button', {
      name: 'Seleccionar archivo CSV o TXT con las URLs de los repositorios',
    })
    const input = document.getElementById('csv-input')
    const clickSpy = vi.spyOn(input, 'click')

    fireEvent.keyDown(dropzone, { key: 'Enter' })

    expect(clickSpy).toHaveBeenCalled()
  })

  it('activa el selector de archivo al presionar espacio en el dropzone', () => {
    render(<CargaView onStart={vi.fn()} errorMsg="" />)
    const dropzone = screen.getByRole('button', {
      name: 'Seleccionar archivo CSV o TXT con las URLs de los repositorios',
    })
    const input = document.getElementById('csv-input')
    const clickSpy = vi.spyOn(input, 'click')

    fireEvent.keyDown(dropzone, { key: ' ' })

    expect(clickSpy).toHaveBeenCalled()
  })

  it('ignora otras teclas', () => {
    render(<CargaView onStart={vi.fn()} errorMsg="" />)
    const dropzone = screen.getByRole('button', {
      name: 'Seleccionar archivo CSV o TXT con las URLs de los repositorios',
    })
    const input = document.getElementById('csv-input')
    const clickSpy = vi.spyOn(input, 'click')

    fireEvent.keyDown(dropzone, { key: 'Tab' })

    expect(clickSpy).not.toHaveBeenCalled()
  })
})

// ─── ReportesView (filtros con label asociado) ─────────────────────────────

const sampleResult = {
  student: 'juan', repo: 'proyecto', score: 80, status: 'ok',
  alerts: [], pattern: 'Trabajo continuo', onTime: true,
  struct: { score: 20, max: 25 }, versioning: { score: 30, max: 40 },
  temporal: { score: 20, max: 25 }, content: { score: 8, max: 10 },
}

describe('ReportesView filtros', () => {
  it('asocia cada label con su select mediante htmlFor/id', () => {
    render(
      <ReportesView
        results={[sampleResult]}
        evalId="123e4567-e89b-12d3-a456-426614174000"
        setTab={vi.fn()}
        onOverride={null}
        onOverrideContent={null}
      />
    )
    expect(screen.getByLabelText('Filtrar por cumplimiento')).toBeInTheDocument()
    expect(screen.getByLabelText('Filtrar por alertas')).toBeInTheDocument()
    expect(screen.getByLabelText('Umbral mínimo')).toBeInTheDocument()
    expect(screen.getByLabelText('Ordenar por')).toBeInTheDocument()
  })
})

// ─── normalizeResult ────────────────────────────────────────────────────────

describe('normalizeResult', () => {
  it('usa Number.parseFloat para el puntaje global, con 0 como fallback', () => {
    expect(normalizeResult({ global_score: '85.5' }).score).toBe(85.5)
    expect(normalizeResult({ global_score: 'no-es-un-numero' }).score).toBe(0)
    expect(normalizeResult({}).score).toBe(0)
  })
})

// ─── App: flujo de inicio de evaluación ────────────────────────────────────

describe('App — inicio de evaluacion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('rechaza un evaluation_id invalido devuelto por el backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ evaluation_id: '../../etc/passwd' }),
    }))

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Cargar repositorios' }))

    fireEvent.change(screen.getByPlaceholderText(/github.com\/estudiante\/proyecto-final/), {
      target: { value: 'https://github.com/juan/proyecto' },
    })
    fireEvent.change(screen.getByPlaceholderText('ghp_...'), { target: { value: 'tok123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar evaluación' }))

    await waitFor(() => {
      expect(screen.getByText('El backend devolvió un identificador de evaluación inválido.')).toBeInTheDocument()
    })
  })
})
