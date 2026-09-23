"""Planilha .xlsx a partir das tabelas de export_csv.py.

Funcao pura, sem dependencia nova: um .xlsx e um zip de alguns XML (Office
Open XML, SpreadsheetML). Escrever so o necessario — uma aba, cabecalho em
negrito e congelado, filtro, largura de coluna e numero como numero — cabe em
poucas linhas e o app continua abrindo offline e sem pip install.

O que muda em relacao ao CSV e justamente o tipo: valor em dinheiro vira
numero com formato "#,##0.00", data vira data do Excel (dd/mm/aaaa),
porcentagem vira fracao com formato "0,00%". Soma, filtro e grafico funcionam
sem converter nada.
"""

import io
import zipfile
from datetime import date
from xml.sax.saxutils import escape

from export_csv import table_values, to_number


EXCEL_EPOCH = date(1899, 12, 30)
MAX_SHEET_NAME = 31

# Indices de cellXfs em styles.xml (a ordem abaixo importa).
STYLE_DEFAULT = 0
STYLE_HEADER = 1
STYLE_MONEY = 2
STYLE_DATE = 3
STYLE_PERCENT = 4
STYLE_QUANTITY = 5

KIND_STYLES = {
    "money": STYLE_MONEY,
    "date": STYLE_DATE,
    "percent": STYLE_PERCENT,
    "quantity": STYLE_QUANTITY,
}

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# numFmtId 4 = "#,##0.00" e 10 = "0.00%" sao embutidos; 164/165 sao nossos.
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>
<numFmt numFmtId="165" formatCode="#,##0.######"/>
</numFmts>
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="2">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def column_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def excel_serial(value):
    """"AAAA-MM-DD" -> numero de serie do Excel; None se nao for data."""
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
    return (parsed - EXCEL_EPOCH).days


def clean_text(value):
    """Texto seguro para XML: sem caracteres de controle, que o Excel recusa."""
    text = str(value)
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)


def text_cell(ref, value, style=STYLE_DEFAULT):
    style_attr = f' s="{style}"' if style else ""
    return (
        f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">'
        f"{escape(clean_text(value))}</t></is></c>"
    )


def number_cell(ref, number, style):
    style_attr = f' s="{style}"' if style else ""
    return f'<c r="{ref}"{style_attr}><v>{repr(float(number))}</v></c>'


def value_cell(ref, value, kind):
    if value is None or value == "":
        return ""
    if kind == "date":
        serial = excel_serial(value)
        return number_cell(ref, serial, STYLE_DATE) if serial is not None else text_cell(ref, value)
    if kind in ("money", "quantity", "percent"):
        number = to_number(value)
        if number is None:
            return ""
        if kind == "percent":
            number = number / 100
        return number_cell(ref, number, KIND_STYLES[kind])
    return text_cell(ref, value)


def column_width(column, values):
    """Largura aproximada: o maior texto da coluna, entre 8 e 50 caracteres."""
    if column.kind == "date":
        longest = 10
    elif column.kind in ("money", "quantity", "percent"):
        longest = 14
    else:
        longest = max((len(str(value)) for value in values if value not in (None, "")), default=0)
    return min(max(longest, len(column.header), 8) + 2, 50)


def sheet_xml(columns, rows):
    last_col = column_letter(len(columns) - 1)
    last_row = len(rows) + 1
    widths = "".join(
        f'<col min="{index + 1}" max="{index + 1}" width="{column_width(column, [row[index] for row in rows])}" customWidth="1"/>'
        for index, column in enumerate(columns)
    )
    header = "".join(
        text_cell(f"{column_letter(index)}1", column.header, STYLE_HEADER)
        for index, column in enumerate(columns)
    )
    body = []
    for row_index, row in enumerate(rows, start=2):
        cells = "".join(
            value_cell(f"{column_letter(col_index)}{row_index}", value, columns[col_index].kind)
            for col_index, value in enumerate(row)
        )
        body.append(f'<row r="{row_index}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_col}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        f"<cols>{widths}</cols>"
        f'<sheetData><row r="1">{header}</row>{"".join(body)}</sheetData>'
        f'<autoFilter ref="A1:{last_col}{last_row}"/>'
        "</worksheet>"
    )


def workbook_xml(sheet_name):
    name = escape(clean_text(sheet_name))[:MAX_SHEET_NAME] or "Planilha"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )


def table_xlsx(sheet_name, columns, items, context=None):
    """Bytes de um .xlsx com uma aba: cabecalho + uma linha por item."""
    rows = table_values(columns, items, context)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook_xml(sheet_name))
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml(columns, rows))
    return buffer.getvalue()
