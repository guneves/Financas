import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Check, CheckCircle2, FileUp, Upload, Wand2 } from 'lucide-react'
import { accountsApi, categoriesApi, importApi, importRulesApi } from '../../lib/dataApi'
import { formatSignedCurrency } from '../../lib/format'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  PageHeader,
  Panel,
  PanelHeader,
  Skeleton,
  cx,
} from '../../components/ui'
import { useQuery, useReportQueryError } from '../../lib/queries'

const COLUMN_ROLES = [
  { key: 'date', label: 'Data' },
  { key: 'description', label: 'Descrição' },
  { key: 'amount', label: 'Valor' },
  { key: 'debit', label: 'Débito' },
  { key: 'credit', label: 'Crédito' },
  { key: 'type', label: 'Tipo' },
]

const STATUS_LABELS = {
  NEW: { label: 'Novo', tone: 'success' },
  DUPLICATE: { label: 'Já importado', tone: 'neutral' },
  ERROR: { label: 'Erro', tone: 'danger' },
}

const defaultOptions = () => ({
  decimal_separator: 'auto',
  delimiter: '',
  invert_sign: false,
  skip_rows: 0,
})

// Extratos de banco brasileiro ainda saem em ISO-8859-1 com frequencia. Le como
// UTF-8 e, se aparecer o caractere de substituicao, le de novo em windows-1252.
async function readFileText(file) {
  const buffer = await file.arrayBuffer()
  const utf8 = new TextDecoder('utf-8').decode(buffer)
  if (!utf8.includes('�')) return utf8
  try {
    return new TextDecoder('windows-1252').decode(buffer)
  } catch {
    return utf8
  }
}

// Sugestao de regra a partir da descricao: as primeiras palavras, sem os
// numeros de autorizacao que mudam a cada compra.
function suggestPattern(description) {
  const words = String(description || '')
    .split(/\s+/)
    .filter((word) => word && !/^\d+$/.test(word) && word !== '*')
  return words.slice(0, 2).join(' ').slice(0, 40)
}

const STEPS = [
  { key: 'file', label: 'Arquivo', hint: 'Conta e extrato' },
  { key: 'review', label: 'Conferir', hint: 'Prévia e categorias' },
  { key: 'done', label: 'Importado', hint: 'Lançamentos gravados' },
]

// Onde a importacao esta: sem previa, escolhendo o arquivo; com previa,
// conferindo; depois de gravar, concluida (a previa recarregada continua
// abaixo, com o que entrou marcado "Já importado").
function Stepper({ current }) {
  const currentIndex = STEPS.findIndex((step) => step.key === current)
  return (
    <ol aria-label="Etapas da importação" className="flex items-center gap-2 sm:gap-3">
      {STEPS.map((step, index) => {
        const done = index < currentIndex || current === 'done'
        const active = index === currentIndex && current !== 'done'
        return (
          <li key={step.key} className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3" aria-current={active ? 'step' : undefined}>
            <span
              className={cx(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold transition-colors',
                done ? 'bg-emerald-100 text-emerald-700' : active ? 'bg-brand text-brand-ink' : 'border border-zinc-200 bg-white text-zinc-500'
              )}
            >
              {done ? <Check className="h-4 w-4" strokeWidth={2.6} /> : index + 1}
            </span>
            <span className="min-w-0">
              <span className={cx('block truncate text-sm font-semibold', active || done ? 'text-zinc-950' : 'text-zinc-500')}>{step.label}</span>
              <span className="hidden truncate text-xs text-zinc-500 sm:block">{step.hint}</span>
            </span>
            {index < STEPS.length - 1 ? <span aria-hidden="true" className="h-px min-w-4 flex-1 bg-zinc-200" /> : null}
          </li>
        )
      })}
    </ol>
  )
}

const NO_ITEMS = []

export default function Importar() {
  const [accountId, setAccountId] = useState('')
  const [options, setOptions] = useState(defaultOptions)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [mapping, setMapping] = useState({})
  const [file, setFile] = useState(null)
  const [content, setContent] = useState('')
  const [preview, setPreview] = useState(null)
  const [selected, setSelected] = useState({})
  const [overrides, setOverrides] = useState({})
  const [parsing, setParsing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const fileInput = useRef(null)
  const [dragging, setDragging] = useState(false)

  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const categoriesQuery = useQuery({ queryKey: ['categorias', 'ativas'], queryFn: () => categoriesApi.list() })
  useReportQueryError(accountsQuery, setError, 'Não foi possível carregar contas e categorias.')
  useReportQueryError(categoriesQuery, setError, 'Não foi possível carregar contas e categorias.')
  const accounts = accountsQuery.data || NO_ITEMS
  const categories = categoriesQuery.data || NO_ITEMS
  const loading = accountsQuery.isPending || categoriesQuery.isPending

  // Conta de destino padrao assim que a lista chega.
  useEffect(() => {
    if (!accounts.length) return
    setAccountId((current) => current || accounts.find((item) => item.is_default)?.id || accounts[0]?.id || '')
  }, [accounts])

  // `filename` vem explicito de handleFile: ali `file` ainda e o arquivo
  // anterior (setFile so vale no proximo render), e o nome decide CSV x OFX.
  const runPreview = async (nextContent, nextOptions = options, nextMapping = mapping, nextAccountId = accountId, filename = file?.name) => {
    if (!nextContent) return
    setParsing(true)
    setError('')
    setResult(null)
    try {
      const body = await importApi.preview({
        content: nextContent,
        filename,
        account_id: nextAccountId || undefined,
        mapping: Object.keys(nextMapping).length ? nextMapping : undefined,
        delimiter: nextOptions.delimiter || undefined,
        decimal_separator: nextOptions.decimal_separator,
        invert_sign: nextOptions.invert_sign,
        skip_rows: Number(nextOptions.skip_rows) || 0,
      })
      setPreview(body)
      // Duplicadas e linhas com erro ficam de fora por padrao: o caso comum e
      // reimportar um arquivo que se sobrepoe ao anterior.
      const nextSelected = {}
      body.rows.forEach((row, index) => {
        nextSelected[index] = row.status === 'NEW'
      })
      setSelected(nextSelected)
      setOverrides({})
    } catch (requestError) {
      setPreview(null)
      setError(requestError.message || 'Não foi possível ler o arquivo.')
    } finally {
      setParsing(false)
    }
  }

  const handleFile = async (event) => {
    await loadFile(event.target.files?.[0])
  }

  const handleDrop = async (event) => {
    event.preventDefault()
    setDragging(false)
    await loadFile(event.dataTransfer?.files?.[0])
  }

  const loadFile = async (picked) => {
    if (!picked) return
    setFile(picked)
    setMapping({})
    const text = await readFileText(picked)
    setContent(text)
    await runPreview(text, options, {}, accountId, picked.name)
  }

  const handleOptionChange = (patch) => {
    const next = { ...options, ...patch }
    setOptions(next)
    runPreview(content, next, mapping, accountId)
  }

  const handleAccountChange = (value) => {
    setAccountId(value)
    runPreview(content, options, mapping, value)
  }

  const handleMappingChange = (role, column) => {
    const next = { ...mapping }
    if (column) next[role] = column
    else delete next[role]
    setMapping(next)
    runPreview(content, options, next, accountId)
  }

  const rowCategory = (row, index) => overrides[index] ?? row.category ?? ''

  const selectedRows = useMemo(() => {
    if (!preview) return []
    return preview.rows
      .map((row, index) => ({ row, index }))
      .filter(({ row, index }) => selected[index] && row.status !== 'ERROR')
      .map(({ row, index }) => ({ ...row, category: rowCategory(row, index) }))
  }, [preview, selected, overrides])

  const missingCategory = selectedRows.some((row) => !row.category)

  const handleImport = async () => {
    setSaving(true)
    setError('')
    try {
      const body = await importApi.commit({
        account_id: accountId || undefined,
        rows: selectedRows.map((row) => ({
          date: row.date,
          amount: row.amount,
          type: row.type,
          description: row.description,
          category: row.category,
          source_id: row.source_id,
          rule_id: row.rule_id || undefined,
        })),
      })
      // Recarrega a previa: o que entrou agora aparece como "Já importado".
      // O resultado vem depois: runPreview zera `result` ao comecar, e antes
      // disto o aviso de sucesso sumia no mesmo instante.
      await runPreview(content, options, mapping, accountId)
      setResult(body)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível importar.')
    } finally {
      setSaving(false)
    }
  }

  const handleCreateRule = async (row, index) => {
    const category = rowCategory(row, index)
    const pattern = suggestPattern(row.description)
    if (!category || !pattern) return
    setError('')
    try {
      await importRulesApi.create({ pattern, category })
      await runPreview(content, options, mapping, accountId)
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar a regra.')
    }
  }

  const reset = () => {
    setFile(null)
    setContent('')
    setPreview(null)
    setSelected({})
    setOverrides({})
    setMapping({})
    setResult(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  const summary = preview?.summary
  const activeCategories = categories.filter((category) => !category.archived_at)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Importar extrato"
        description="CSV ou OFX do banco. Nada é gravado antes de você conferir a prévia."
      />

      <Panel className="px-5 py-4 sm:px-6">
        <Stepper current={result ? 'done' : preview ? 'review' : 'file'} />
      </Panel>

      <AlertMessage message={error} onDismiss={() => setError('')} />

      {result ? (
        <AlertMessage tone="success">
          {result.created} lançamento(s) importado(s).
          {result.skipped ? ` ${result.skipped} já existia(m) e foi(ram) ignorado(s).` : ''}
        </AlertMessage>
      ) : null}

      <Panel>
        <PanelHeader
          title="1. Arquivo"
          description="O banco exporta o extrato em CSV ou OFX; os dois servem."
          actions={file ? <Button variant="secondary" onClick={reset}>{result ? 'Importar outro arquivo' : 'Trocar arquivo'}</Button> : null}
        />
        <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
          <Field label="Conta de destino" hint="Todos os lançamentos do arquivo entram nesta conta.">
            {loading ? <Skeleton className="h-11 w-full" /> : (
              <select value={accountId} onChange={(event) => handleAccountChange(event.target.value)} className="app-select">
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            )}
          </Field>
          {/* Input nativo escondido: o botao do navegador vem no idioma dele
              ("Choose File") e repetia o nome do arquivo abaixo. */}
          <Field label="Arquivo" hint="Formatos aceitos: .csv, .txt, .ofx">
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.txt,.ofx,.ofc"
              onChange={handleFile}
              className="sr-only"
            />
            {/* O Field ja e um <label>: clicar aqui abre o seletor do input. */}
            <div
              onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              className={cx(
                'flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-dashed px-3 py-2 text-sm transition',
                dragging ? 'border-emerald-500 bg-emerald-50' : 'border-zinc-300 bg-white hover:border-zinc-400 hover:bg-zinc-50'
              )}
            >
              <FileUp className="h-4 w-4 shrink-0 text-zinc-500" />
              {file ? (
                <span className="min-w-0 flex-1 truncate font-medium text-zinc-900" title={file.name}>{file.name}</span>
              ) : (
                <span className="min-w-0 flex-1 text-zinc-600">Escolher arquivo ou arrastar para cá</span>
              )}
              <span className="shrink-0 font-semibold text-zinc-700">{file ? 'Trocar' : 'Escolher'}</span>
            </div>
          </Field>
        </div>

        {preview ? (
          <Collapsible
            label="Opções de leitura"
            icon={Wand2}
            variant="secondary"
            open={optionsOpen}
            onOpenChange={setOptionsOpen}
            className="border-t border-zinc-100 px-5 py-4"
          >
            <div className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-4">
              <Field label="Separador decimal">
                <select
                  value={options.decimal_separator}
                  onChange={(event) => handleOptionChange({ decimal_separator: event.target.value })}
                  className="app-select"
                >
                  <option value="auto">Detectar</option>
                  <option value=",">Vírgula (1.234,56)</option>
                  <option value=".">Ponto (1,234.56)</option>
                </select>
              </Field>
              <Field label="Separador de colunas" hint={preview.delimiter ? `Detectado: "${preview.delimiter}"` : 'Só vale para CSV'}>
                <select
                  value={options.delimiter}
                  onChange={(event) => handleOptionChange({ delimiter: event.target.value })}
                  className="app-select"
                >
                  <option value="">Detectar</option>
                  <option value=";">Ponto e vírgula</option>
                  <option value=",">Vírgula</option>
                  <option value={'\t'}>Tabulação</option>
                  <option value="|">Barra vertical</option>
                </select>
              </Field>
              <Field label="Linhas a pular" hint="Cabeçalho de relatório antes da tabela.">
                <input
                  type="number"
                  min="0"
                  value={options.skip_rows}
                  onChange={(event) => handleOptionChange({ skip_rows: event.target.value })}
                  className="app-input"
                />
              </Field>
              <Field label="Sinal" hint="Se entradas e saídas saírem trocadas.">
                <label className="flex h-11 items-center gap-2 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    checked={options.invert_sign}
                    onChange={(event) => handleOptionChange({ invert_sign: event.target.checked })}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600"
                  />
                  Inverter
                </label>
              </Field>
            </div>

            {preview.columns?.length ? (
              <div className="mt-4 grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-3">
                {COLUMN_ROLES.map((role) => (
                  <Field key={role.key} label={role.label}>
                    <select
                      value={mapping[role.key] ?? preview.columns[preview.mapping?.[role.key]] ?? ''}
                      onChange={(event) => handleMappingChange(role.key, event.target.value)}
                      className="app-select"
                    >
                      <option value="">—</option>
                      {preview.columns.map((column) => (
                        <option key={column} value={column}>{column}</option>
                      ))}
                    </select>
                  </Field>
                ))}
              </div>
            ) : null}
          </Collapsible>
        ) : null}
      </Panel>

      {parsing ? (
        <Panel><Skeleton className="h-40 w-full" /></Panel>
      ) : null}

      {preview && !parsing ? (
        <Panel className="overflow-clip">
          <PanelHeader
            title="2. Conferir"
            description={`${summary.total} linha(s): ${summary.new} nova(s), ${summary.duplicates} já importada(s), ${summary.errors} com erro.`}
            actions={(
              <Button icon={Upload} onClick={handleImport} loading={saving} disabled={!selectedRows.length || missingCategory}>
                Importar {selectedRows.length || ''}
              </Button>
            )}
          />

          {missingCategory ? (
            <AlertMessage tone="warning" message="Escolha uma categoria para cada linha selecionada." className="mx-5 mt-4" />
          ) : null}
          {preview.truncated ? (
            <AlertMessage tone="warning" message="O arquivo tem mais linhas do que cabe em uma importação; as primeiras foram lidas." className="mx-5 mt-4" />
          ) : null}

          {preview.rows.length ? (
            <div className="divide-y divide-zinc-100">
              {preview.rows.map((row, index) => {
                const status = STATUS_LABELS[row.status] || STATUS_LABELS.ERROR
                const isError = row.status === 'ERROR'
                return (
                  <div key={`${row.line}-${index}`} className={cx('flex flex-col gap-3 px-5 py-3 sm:flex-row sm:items-center', isError && 'bg-rose-50/50')}>
                    <input
                      type="checkbox"
                      checked={Boolean(selected[index])}
                      disabled={isError}
                      onChange={(event) => setSelected({ ...selected, [index]: event.target.checked })}
                      aria-label={`Importar linha ${row.line}`}
                      className="h-4 w-4 shrink-0 rounded border-zinc-300 text-emerald-600 disabled:opacity-40"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-zinc-900">{row.description || '(sem descrição)'}</p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                        <span>Linha {row.line}</span>
                        {row.date ? <span>{row.date.split('-').reverse().join('/')}</span> : null}
                        <Badge tone={status.tone}>{status.label}</Badge>
                        {row.error ? <span className="text-rose-600">{row.error}</span> : null}
                        {row.category_source === 'RULE' ? <span className="text-emerald-600">regra: {row.rule_pattern}</span> : null}
                      </p>
                    </div>
                    {!isError ? (
                      <div className="flex items-center gap-2">
                        <select
                          value={rowCategory(row, index)}
                          onChange={(event) => setOverrides({ ...overrides, [index]: event.target.value })}
                          className="app-select h-10 w-44"
                          aria-label={`Categoria da linha ${row.line}`}
                        >
                          <option value="">Categoria...</option>
                          {activeCategories.map((category) => (
                            <option key={category.id} value={category.name}>{category.name}</option>
                          ))}
                        </select>
                        <Button
                          variant="subtle"
                          size="sm"
                          onClick={() => handleCreateRule(row, index)}
                          disabled={!rowCategory(row, index) || row.category_source === 'RULE'}
                          title="Criar uma regra para categorizar lançamentos parecidos"
                        >
                          Criar regra
                        </Button>
                        <span className={cx('w-28 text-right text-sm font-bold', row.type === 'INCOME' ? 'text-emerald-600' : 'text-zinc-950')}>
                          {formatSignedCurrency(row.amount, row.type === 'INCOME' ? 1 : -1)}
                        </span>
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          ) : (
            <EmptyState icon={AlertTriangle} title="Nenhuma linha" message="O arquivo não tem lançamentos legíveis." className="m-5" />
          )}
        </Panel>
      ) : null}

      {!preview && !parsing ? (
        <EmptyState
          icon={FileUp}
          title="Escolha um arquivo"
          message="Exporte o extrato do banco em CSV ou OFX e selecione o arquivo acima. A prévia mostra o que entraria antes de gravar."
        />
      ) : null}

      <p className="flex items-center gap-2 text-xs text-zinc-500">
        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
        Reimportar o mesmo extrato não duplica nada: cada linha carrega uma assinatura própria.
        As regras de categorização ficam em Ajustes → Regras de importação.
      </p>
    </div>
  )
}
