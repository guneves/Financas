import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileUp, Upload, Wand2 } from 'lucide-react'
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

export default function Importar() {
  const [accounts, setAccounts] = useState([])
  const [categories, setCategories] = useState([])
  const [accountId, setAccountId] = useState('')
  const [options, setOptions] = useState(defaultOptions)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [mapping, setMapping] = useState({})
  const [file, setFile] = useState(null)
  const [content, setContent] = useState('')
  const [preview, setPreview] = useState(null)
  const [selected, setSelected] = useState({})
  const [overrides, setOverrides] = useState({})
  const [loading, setLoading] = useState(true)
  const [parsing, setParsing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const fileInput = useRef(null)

  useEffect(() => {
    let active = true
    Promise.all([accountsApi.list(), categoriesApi.list()])
      .then(([accountData, categoryData]) => {
        if (!active) return
        const list = accountData || []
        setAccounts(list)
        setCategories(categoryData || [])
        setAccountId((current) => current || list.find((item) => item.is_default)?.id || list[0]?.id || '')
      })
      .catch((requestError) => {
        if (active) setError(requestError.message || 'Não foi possível carregar contas e categorias.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const runPreview = async (nextContent, nextOptions = options, nextMapping = mapping, nextAccountId = accountId) => {
    if (!nextContent) return
    setParsing(true)
    setError('')
    setResult(null)
    try {
      const body = await importApi.preview({
        content: nextContent,
        filename: file?.name,
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
    const picked = event.target.files?.[0]
    if (!picked) return
    setFile(picked)
    setMapping({})
    const text = await readFileText(picked)
    setContent(text)
    await runPreview(text, options, {}, accountId)
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
      setResult(body)
      // Recarrega a previa: o que entrou agora aparece como "Já importado".
      await runPreview(content, options, mapping, accountId)
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

      <AlertMessage message={error} onDismiss={() => setError('')} />

      {result ? (
        <AlertMessage tone="success">
          {result.created} lançamento(s) importado(s).
          {result.skipped ? ` ${result.skipped} já existia(m) e foi(ram) ignorado(s).` : ''}
        </AlertMessage>
      ) : null}

      <Panel>
        <PanelHeader
          title="Arquivo"
          description="O banco exporta o extrato em CSV ou OFX; os dois servem."
          actions={file ? <Button variant="secondary" onClick={reset}>Trocar arquivo</Button> : null}
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
          <Field label="Arquivo" hint={file ? file.name : 'Formatos aceitos: .csv, .txt, .ofx'}>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.txt,.ofx,.ofc"
              onChange={handleFile}
              className="app-input file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-zinc-700"
            />
          </Field>
        </div>

        {preview ? (
          <Collapsible
            label="Opções de leitura"
            icon={Wand2}
            variant="secondary"
            open={optionsOpen}
            onOpenChange={setOptionsOpen}
            className="mt-4"
          >
            <div className="grid grid-cols-1 gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-4">
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
              <div className="mt-4 grid grid-cols-1 gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-3">
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
        <Panel>
          <PanelHeader
            title="Prévia"
            description={`${summary.total} linha(s): ${summary.new} nova(s), ${summary.duplicates} já importada(s), ${summary.errors} com erro.`}
            actions={(
              <Button icon={Upload} onClick={handleImport} loading={saving} disabled={!selectedRows.length || missingCategory}>
                Importar {selectedRows.length || ''}
              </Button>
            )}
          />

          {missingCategory ? (
            <AlertMessage tone="warning" message="Escolha uma categoria para cada linha selecionada." className="mb-4" />
          ) : null}
          {preview.truncated ? (
            <AlertMessage tone="warning" message="O arquivo tem mais linhas do que cabe em uma importação; as primeiras foram lidas." className="mb-4" />
          ) : null}

          {preview.rows.length ? (
            <div className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
              {preview.rows.map((row, index) => {
                const status = STATUS_LABELS[row.status] || STATUS_LABELS.ERROR
                const isError = row.status === 'ERROR'
                return (
                  <div key={`${row.line}-${index}`} className={cx('flex flex-col gap-3 p-3 sm:flex-row sm:items-center', isError && 'bg-rose-50/50')}>
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
            <EmptyState icon={AlertTriangle} title="Nenhuma linha" message="O arquivo não tem lançamentos legíveis." />
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
