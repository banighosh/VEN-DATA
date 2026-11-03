"""Generate a Power BI Project (PBIP: TMDL semantic model + PBIR report) for the Adidas US Sales workbook.

Usage: python build_pbip.py <output_dir> "<absolute Windows path to Adidas US Sales Datasets.xlsx>"
Open the generated .pbip in Power BI Desktop, refresh, then File > Save as > .pbix.
"""
from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

PROJECT = "Adidas Sales Analytics"
NS = uuid.UUID("5b3c1f9e-6a43-4d6c-9d2a-7f1f0e8b2c11")


def tag(*parts: str) -> str:
    """Deterministic lineage tags so regenerated projects diff cleanly."""
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    return f"'{name}'" if any(c in name for c in " .,'=:[]()×") or not name.isidentifier() else name


# ============================================================================ semantic model
SALES_M = r'''let
    Source = Excel.Workbook(File.Contents(ExcelFilePath), null, true),
    Sheet = Source{[Item="Cleaned_Table",Kind="Sheet"]}[Data],
    Promoted = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true]),
    Selected = Table.SelectColumns(Promoted, {"Retailer", "Retailer ID", "Invoice Date", "Region", "State", "City", "Product", "Price per Unit", "Units Sold", "Total Sales", "Operating Profit", "Operating Margin", "Sales Method", "Gender", "Product Category", "Product Type"}),
    Typed = Table.TransformColumnTypes(Selected, {{"Retailer", type text}, {"Retailer ID", Int64.Type}, {"Invoice Date", type date}, {"Region", type text}, {"State", type text}, {"City", type text}, {"Product", type text}, {"Price per Unit", type number}, {"Units Sold", Int64.Type}, {"Total Sales", type number}, {"Operating Profit", type number}, {"Operating Margin", type number}, {"Sales Method", type text}, {"Gender", type text}, {"Product Category", type text}, {"Product Type", type text}}),
    Trimmed = Table.TransformColumns(Typed, {{"Retailer", Text.Trim, type text}, {"Region", Text.Trim, type text}, {"State", Text.Trim, type text}, {"City", Text.Trim, type text}, {"Product", Text.Trim, type text}, {"Sales Method", Text.Trim, type text}}),
    WithRowId = Table.AddIndexColumn(Trimmed, "Row ID", 1, 1, Int64.Type),
    WithExpected = Table.AddColumn(WithRowId, "Price x Units", each [Price per Unit] * [Units Sold], type number),
    WithCheck = Table.AddColumn(WithExpected, "Revenue Check", each
        if [Price x Units] = null or [Price x Units] = 0 then "Zero price or units"
        else if Number.Abs([Total Sales] - [Price x Units]) <= 0.01 * [Price x Units] then "Matches price × units"
        else if Number.Abs([Total Sales] - 10 * [Price x Units]) <= 0.01 * 10 * [Price x Units] then "Exactly 10× price × units"
        else "Other mismatch", type text),
    WithCost = Table.AddColumn(WithCheck, "Implied Cost", each [Total Sales] - [Operating Profit], type number),
    WithCityKey = Table.AddColumn(WithCost, "City Key", each [City] & ", " & [State], type text)
in
    WithCityKey'''

DIM_M = {
    "Product": '''let
    Source = Sales,
    Columns = Table.SelectColumns(Source, {"Product", "Product Category", "Product Type", "Gender"}),
    Distinct = Table.Distinct(Columns, {"Product"})
in
    Distinct''',
    "Retailer": '''let
    Source = Sales,
    Columns = Table.SelectColumns(Source, {"Retailer"}),
    Distinct = Table.Distinct(Columns)
in
    Distinct''',
    "Geography": '''let
    Source = Sales,
    Columns = Table.SelectColumns(Source, {"City Key", "City", "State", "Region"}),
    Distinct = Table.Distinct(Columns, {"City Key"})
in
    Distinct''',
    "Sales Method": '''let
    Source = Sales,
    Columns = Table.SelectColumns(Source, {"Sales Method"}),
    Distinct = Table.Distinct(Columns),
    WithOrder = Table.AddColumn(Distinct, "Sales Method Order", each if [Sales Method] = "In-Store" then 1 else if [Sales Method] = "Outlet" then 2 else 3, Int64.Type)
in
    WithOrder''',
}

CALENDAR_DAX = '''
VAR MinYear = YEAR ( MIN ( Sales[Invoice Date] ) )
VAR MaxYear = YEAR ( MAX ( Sales[Invoice Date] ) )
RETURN
    ADDCOLUMNS (
        CALENDAR ( DATE ( MinYear, 1, 1 ), DATE ( MaxYear, 12, 31 ) ),
        "Year", YEAR ( [Date] ),
        "Quarter", "Q" & QUARTER ( [Date] ),
        "Year Quarter", YEAR ( [Date] ) & " Q" & QUARTER ( [Date] ),
        "Year Quarter Number", YEAR ( [Date] ) * 10 + QUARTER ( [Date] ),
        "Month Number", MONTH ( [Date] ),
        "Month", FORMAT ( [Date], "MMM" ),
        "Year Month", FORMAT ( [Date], "MMM yyyy" ),
        "Year Month Number", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
        "Weekday", FORMAT ( [Date], "ddd" ),
        "Weekday Number", WEEKDAY ( [Date], 2 )
    )
'''

CUR = r"\$#,0;(\$#,0);\$#,0"
CUR2 = r"\$#,0.00;(\$#,0.00);\$#,0.00"
PCT = "0.0%;-0.0%;0.0%"
INT = "#,0"

# (name, dataType, formatString, summarizeBy, hidden, extra)
SALES_COLUMNS = [
    ("Row ID", "int64", "0", "none", True, {}),
    ("Retailer", "string", None, "none", True, {}),
    ("Retailer ID", "int64", "0", "none", True, {"description": "Not a unique key: the same ID is shared by several retailers."}),
    ("Invoice Date", "dateTime", "Short Date", "none", True, {"date": True}),
    ("Region", "string", None, "none", True, {}),
    ("State", "string", None, "none", True, {}),
    ("City", "string", None, "none", True, {}),
    ("City Key", "string", None, "none", True, {}),
    ("Product", "string", None, "none", True, {}),
    ("Price per Unit", "double", CUR2, "none", False, {}),
    ("Units Sold", "int64", INT, "sum", False, {}),
    ("Total Sales", "double", CUR, "sum", False, {"description": "Revenue as reported in the source (see the Data Quality page)."}),
    ("Operating Profit", "double", CUR, "sum", False, {}),
    ("Operating Margin", "double", PCT, "none", False, {}),
    ("Sales Method", "string", None, "none", True, {}),
    ("Gender", "string", None, "none", True, {}),
    ("Product Category", "string", None, "none", True, {}),
    ("Product Type", "string", None, "none", True, {}),
    ("Price x Units", "double", CUR, "sum", False, {}),
    ("Revenue Check", "string", None, "none", False, {"description": "Whether Total Sales equals Price per Unit × Units Sold (within 1%)."}),
    ("Implied Cost", "double", CUR, "sum", False, {"description": "Total Sales − Operating Profit. The source has no cost column."}),
]

DIM_COLUMNS = {
    "Product": [("Product", "string", None, "none", False, {}), ("Product Category", "string", None, "none", False, {}),
                ("Product Type", "string", None, "none", False, {}), ("Gender", "string", None, "none", False, {})],
    "Retailer": [("Retailer", "string", None, "none", False, {})],
    "Geography": [("City Key", "string", None, "none", True, {}), ("City", "string", None, "none", False, {"dataCategory": "City"}),
                  ("State", "string", None, "none", False, {"dataCategory": "StateOrProvince"}), ("Region", "string", None, "none", False, {})],
    "Sales Method": [("Sales Method", "string", None, "none", False, {"sortBy": "Sales Method Order"}),
                     ("Sales Method Order", "int64", "0", "none", True, {})],
}

CALENDAR_COLUMNS = [
    ("Date", "dateTime", "Short Date", "none", False, {"key": True, "date": True}),
    ("Year", "int64", "0", "none", False, {}),
    ("Quarter", "string", None, "none", False, {}),
    ("Year Quarter", "string", None, "none", False, {"sortBy": "Year Quarter Number"}),
    ("Year Quarter Number", "int64", "0", "none", True, {}),
    ("Month Number", "int64", "0", "none", True, {}),
    ("Month", "string", None, "none", False, {"sortBy": "Month Number"}),
    ("Year Month", "string", None, "none", False, {"sortBy": "Year Month Number"}),
    ("Year Month Number", "int64", "0", "none", True, {}),
    ("Weekday", "string", None, "none", False, {"sortBy": "Weekday Number"}),
    ("Weekday Number", "int64", "0", "none", True, {}),
]

ONE_YEAR = "COUNTROWS ( VALUES ( 'Calendar'[Year] ) ) = 1"


def py(measure: str) -> str:
    # Prior-year values only when the context is a single year (or finer); a multi-year
    # context has no meaningful "prior year", so the measure stays blank instead of misleading.
    return f"IF ( {ONE_YEAR}, CALCULATE ( [{measure}], SAMEPERIODLASTYEAR ( 'Calendar'[Date] ) ) )"


def fmt_prev(kind: str) -> str:
    """DAX that renders PrevValue compactly; suffixes are concatenated so they can't be read as format codes."""
    return {
        "money_m": 'FORMAT ( PrevValue / 1000000, "$#,0.0" ) & "M"',
        "count_k": 'FORMAT ( PrevValue / 1000, "#,0.0" ) & "K"',
        "pct": 'FORMAT ( PrevValue, "0.0%" )',
        "int": 'FORMAT ( PrevValue, "#,0" )',
        "money": 'FORMAT ( PrevValue, "$#,0" )',
    }[kind]


def vs_text(cur: str, prev: str, kind: str, prev_fmt: str) -> str:
    if kind == "pp":
        delta = f"[{cur}] - [{prev}]"
        fmt = '"+0.0 pp;-0.0 pp;0.0 pp"'
        scale = " * 100"
    else:
        delta = f"DIVIDE ( [{cur}] - [{prev}], [{prev}] )"
        fmt = '"+0.0%;-0.0%;0.0%"'
        scale = ""
    return f'''
VAR PrevValue = [{prev}]
VAR Delta = {delta}
RETURN
    IF (
        NOT ( {ONE_YEAR} ),
        "Select one year to compare",
        IF (
            ISBLANK ( PrevValue ),
            "No prior-year data",
            IF ( Delta >= 0, UNICHAR ( 9650 ), UNICHAR ( 9660 ) ) & " " & FORMAT ( Delta{scale}, {fmt} ) & " vs prior year (" & {fmt_prev(prev_fmt)} & ")"
        )
    )
'''


def color(cur: str, prev: str, kind: str, up_good: bool = True) -> str:
    delta = f"[{cur}] - [{prev}]"
    good, bad = ('"#0B7A3B"', '"#B9312A"') if up_good else ('"#B9312A"', '"#0B7A3B"')
    return f'''
VAR PrevValue = [{prev}]
RETURN
    IF ( ISBLANK ( PrevValue ) || NOT ( {ONE_YEAR} ), "#6F7C92", IF ( {delta} >= 0, {good}, {bad} ) )
'''


MEASURES: list[tuple[str, str, str | None, str]] = [
    # name, DAX, format, display folder
    ("Total Revenue", "SUM ( Sales[Total Sales] )", CUR, "1. Core"),
    ("Units Sold", "SUM ( Sales[Units Sold] )", INT, "1. Core"),
    ("Operating Profit", "SUM ( Sales[Operating Profit] )", CUR, "1. Core"),
    ("Operating Margin", "DIVIDE ( [Operating Profit], [Total Revenue] )", PCT, "1. Core"),
    ("Implied Cost", "[Total Revenue] - [Operating Profit]", CUR, "1. Core"),
    ("Transactions", "COUNTROWS ( Sales )", INT, "1. Core"),
    ("Avg Transaction Value", "DIVIDE ( [Total Revenue], [Transactions] )", CUR, "1. Core"),
    ("Active Retailers", "DISTINCTCOUNT ( Sales[Retailer] )", "0", "1. Core"),
    ("Units per Transaction", "DIVIDE ( [Units Sold], [Transactions] )", "#,0.0", "1. Core"),
    ("Revenue per Unit", "DIVIDE ( [Total Revenue], [Units Sold] )", CUR2, "1. Core"),
    ("Revenue Share", "DIVIDE ( [Total Revenue], CALCULATE ( [Total Revenue], ALLSELECTED () ) )", PCT, "1. Core"),
    ("Revenue PY", py("Total Revenue"), CUR, "2. Prior year"),
    ("Units PY", py("Units Sold"), INT, "2. Prior year"),
    ("Profit PY", py("Operating Profit"), CUR, "2. Prior year"),
    ("Margin PY", py("Operating Margin"), PCT, "2. Prior year"),
    ("Transactions PY", py("Transactions"), INT, "2. Prior year"),
    ("Avg Transaction Value PY", py("Avg Transaction Value"), CUR, "2. Prior year"),
    ("Active Retailers PY", py("Active Retailers"), "0", "2. Prior year"),
    ("Revenue YoY %", "DIVIDE ( [Total Revenue] - [Revenue PY], [Revenue PY] )", PCT, "2. Prior year"),
    ("Profit YoY %", "DIVIDE ( [Operating Profit] - [Profit PY], [Profit PY] )", PCT, "2. Prior year"),
    ("Margin Change (pp)", "IF ( NOT ISBLANK ( [Margin PY] ), ( [Operating Margin] - [Margin PY] ) * 100 )", "+0.0;-0.0;0.0", "2. Prior year"),
    ("Revenue YTD", "TOTALYTD ( [Total Revenue], 'Calendar'[Date] )", CUR, "2. Prior year"),
    ("Revenue PY YTD", "CALCULATE ( [Revenue YTD], SAMEPERIODLASTYEAR ( 'Calendar'[Date] ) )", CUR, "2. Prior year"),
    ("Revenue vs PY", vs_text("Total Revenue", "Revenue PY", "pct", "money_m"), None, "3. KPI labels"),
    ("Units vs PY", vs_text("Units Sold", "Units PY", "pct", "count_k"), None, "3. KPI labels"),
    ("Profit vs PY", vs_text("Operating Profit", "Profit PY", "pct", "money_m"), None, "3. KPI labels"),
    ("Margin vs PY", vs_text("Operating Margin", "Margin PY", "pp", "pct"), None, "3. KPI labels"),
    ("Transactions vs PY", vs_text("Transactions", "Transactions PY", "pct", "int"), None, "3. KPI labels"),
    ("ATV vs PY", vs_text("Avg Transaction Value", "Avg Transaction Value PY", "pct", "money"), None, "3. KPI labels"),
    ("Retailers vs PY", vs_text("Active Retailers", "Active Retailers PY", "pct", "int"), None, "3. KPI labels"),
    ("Growth Label", '''
VAR PrevValue = [Revenue PY]
RETURN
    IF (
        NOT ( ''' + ONE_YEAR + ''' ),
        "Select one year to see growth",
        IF ( ISBLANK ( PrevValue ), "No prior-year data", "Revenue growth vs " & FORMAT ( MIN ( 'Calendar'[Year] ) - 1, "0" ) )
    )
''', None, "3. KPI labels"),
    ("Revenue Color", color("Total Revenue", "Revenue PY", "pct"), None, "3. KPI labels"),
    ("Units Color", color("Units Sold", "Units PY", "pct"), None, "3. KPI labels"),
    ("Profit Color", color("Operating Profit", "Profit PY", "pct"), None, "3. KPI labels"),
    ("Margin Color", color("Operating Margin", "Margin PY", "pp"), None, "3. KPI labels"),
    ("Transactions Color", color("Transactions", "Transactions PY", "pct"), None, "3. KPI labels"),
    ("ATV Color", color("Avg Transaction Value", "Avg Transaction Value PY", "pct"), None, "3. KPI labels"),
    ("Retailers Color", color("Active Retailers", "Active Retailers PY", "pct"), None, "3. KPI labels"),
    ("First Purchase", "CALCULATE ( MIN ( Sales[Invoice Date] ), REMOVEFILTERS ( 'Calendar' ) )", "dd mmm yyyy", "4. Retailers"),
    ("Last Purchase", "CALCULATE ( MAX ( Sales[Invoice Date] ), REMOVEFILTERS ( 'Calendar' ) )", "dd mmm yyyy", "4. Retailers"),
    ("Revenue (Price × Units)", "SUM ( Sales[Price x Units] )", CUR, "5. Data quality"),
    ("Revenue Gap", "[Total Revenue] - [Revenue (Price × Units)]", CUR, "5. Data quality"),
    ("Rows Failing Revenue Check", 'CALCULATE ( COUNTROWS ( Sales ), Sales[Revenue Check] <> "Matches price × units" )', INT, "5. Data quality"),
    ("% Rows Failing Revenue Check", "DIVIDE ( [Rows Failing Revenue Check], [Transactions] )", PCT, "5. Data quality"),
]


def column_block(name: str, dtype: str, fmt: str | None, summarize: str, hidden: bool, extra: dict, table: str,
                 calculated: bool = False) -> str:
    lines = [f"\tcolumn {q(name)}"]
    lines.append(f"\t\tdataType: {dtype}")
    if extra.get("key"):
        lines.append("\t\tisKey")
    if hidden:
        lines.append("\t\tisHidden")
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    if extra.get("description"):
        pass
    lines.append(f"\t\tlineageTag: {tag(table, name)}")
    if extra.get("dataCategory"):
        lines.append(f"\t\tdataCategory: {extra['dataCategory']}")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    if calculated:
        lines.append("\t\tisNameInferred")
        lines.append(f"\t\tsourceColumn: [{name}]")
    else:
        lines.append(f"\t\tsourceColumn: {name}")
    if extra.get("sortBy"):
        lines.append(f"\t\tsortByColumn: {q(extra['sortBy'])}")
    lines.append("")
    if extra.get("sortBy"):
        lines.append("\t\tchangedProperty = SortByColumn")
        lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    if extra.get("date"):
        lines.append("")
        lines.append("\t\tannotation UnderlyingDateTimeDataType = Date")
    out = "\n".join(lines) + "\n"
    if extra.get("description"):
        out = f"\t/// {extra['description']}\n" + out
    return out


def indent_code(code: str, tabs: int) -> str:
    pad = "\t" * tabs
    return "\n".join(pad + line if line.strip() else "" for line in code.strip("\n").splitlines())


def m_table(name: str, columns: list, m_code: str, hidden_table: bool = False) -> str:
    out = [f"table {q(name)}", f"\tlineageTag: {tag(name)}", ""]
    if hidden_table:
        out.insert(1, "\tisHidden")
    for c in columns:
        out.append(column_block(*c, table=name))
    out.append(f"\tpartition {q(name)} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out.append(indent_code(m_code, 4))
    out.append("")
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def calendar_table() -> str:
    out = ["table Calendar", f"\tlineageTag: {tag('Calendar')}", "\tdataCategory: Time", ""]
    for c in CALENDAR_COLUMNS:
        out.append(column_block(*c, table="Calendar", calculated=True))
    out.append("\tpartition Calendar = calculated")
    out.append("\t\tmode: import")
    out.append("\t\tsource = ```")
    out.append(indent_code(CALENDAR_DAX, 4))
    out.append("\t\t\t\t```")
    out.append("")
    out.append("\tannotation PBI_Id = " + uuid.uuid5(NS, "calendar-id").hex)
    out.append("")
    return "\n".join(out)


def measures_table() -> str:
    out = ["table _Measures", f"\tlineageTag: {tag('_Measures')}", ""]
    for name, dax, fmt, folder in MEASURES:
        body = dax.strip("\n")
        if "\n" in body:
            out.append(f"\tmeasure {q(name)} = ```")
            out.append(indent_code(body, 3))
            out.append("\t\t\t```")
        else:
            out.append(f"\tmeasure {q(name)} = {body}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tdisplayFolder: {folder}")
        out.append(f"\t\tlineageTag: {tag('_Measures', name)}")
        if fmt and fmt.startswith("\\$"):
            out.append("")
            out.append('\t\tannotation PBI_FormatHint = {"currencyCulture":"en-US"}')
        out.append("")
    out.append("\tcolumn Value")
    out.append("\t\tisHidden")
    out.append("\t\tformatString: 0")
    out.append(f"\t\tlineageTag: {tag('_Measures', 'Value')}")
    out.append("\t\tsummarizeBy: sum")
    out.append("\t\tisNameInferred")
    out.append("\t\tsourceColumn: [Value]")
    out.append("")
    out.append("\t\tannotation SummarizationSetBy = Automatic")
    out.append("")
    out.append("\tpartition _Measures = calculated")
    out.append("\t\tmode: import")
    out.append("\t\tsource = ```")
    out.append("\t\t\t\t{0}")
    out.append("\t\t\t\t```")
    out.append("")
    out.append("\tannotation PBI_Id = " + uuid.uuid5(NS, "measures-id").hex)
    out.append("")
    return "\n".join(out)


RELATIONSHIPS = [
    ("Sales", "Invoice Date", "Calendar", "Date"),
    ("Sales", "Product", "Product", "Product"),
    ("Sales", "Retailer", "Retailer", "Retailer"),
    ("Sales", "City Key", "Geography", "City Key"),
    ("Sales", "Sales Method", "Sales Method", "Sales Method"),
]


def write_model(root: Path, excel_path: str) -> None:
    sm = root / f"{PROJECT}.SemanticModel"
    d = sm / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (sm / "definition.pbism").write_text(json.dumps({"version": "4.1", "settings": {}}, indent=2))
    (sm / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId": tag("logical", "model")}}, indent=2))
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n\n")
    tables = ["Sales", "Product", "Retailer", "Geography", "Sales Method", "Calendar", "_Measures"]
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        'annotation PBI_QueryOrder = ["ExcelFilePath","Sales","Product","Retailer","Geography","Sales Method"]',
        "",
    ] + [f"ref table {q(t)}" for t in tables] + [""]
    (d / "model.tmdl").write_text("\n".join(model) + "\n")
    path_literal = excel_path.replace('"', '""')
    (d / "expressions.tmdl").write_text(
        f'/// Full path to "Adidas US Sales Datasets.xlsx". Change it in Transform data > Edit parameters.\n'
        f'expression ExcelFilePath = "{path_literal}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag('ExcelFilePath')}\n\n\tannotation PBI_ResultType = Text\n\n")
    (d / "tables" / "Sales.tmdl").write_text(m_table("Sales", SALES_COLUMNS, SALES_M))
    for name, code in DIM_M.items():
        (d / "tables" / f"{name}.tmdl").write_text(m_table(name, DIM_COLUMNS[name], code))
    (d / "tables" / "Calendar.tmdl").write_text(calendar_table())
    (d / "tables" / "_Measures.tmdl").write_text(measures_table())
    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {tag('rel', ft, fc)}", f"\tfromColumn: {q(ft)}.{q(fc)}", f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel) + "\n")


# ============================================================================ report (PBIR)
VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.5.0/schema.json"
NAVY, INK, MUTED, WHITE, LINE = "#0B1F3A", "#1E2532", "#6F7C92", "#FFFFFF", "#E2E7EE"


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def s(text: str) -> dict:  # string literal
    return lit("'" + text.replace("'", "''") + "'")


def b(v: bool) -> dict:
    return lit("true" if v else "false")


def n(v: float) -> dict:
    return lit(f"{v}D")


def solid(hex_color: str) -> dict:
    return {"solid": {"color": s(hex_color)}}


def measure_color(m: str) -> dict:
    return {"solid": {"color": {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": m}}}}}


def field(kind: str, entity: str, prop: str) -> dict:
    key = "Measure" if kind == "m" else "Column"
    return {key: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def F(spec: str) -> tuple[str, str, str]:
    """'m:Total Revenue' -> measure in _Measures; 'Table[Column]' -> column."""
    if spec.startswith("m:"):
        return ("m", "_Measures", spec[2:])
    t, c = spec.split("[", 1)
    return ("c", t, c.rstrip("]"))


def projection(spec: str, active: bool | None = None) -> dict:
    kind, ent, prop = F(spec)
    p = {"field": field(kind, ent, prop), "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}
    if active is not None:
        p["active"] = active
    return p


class Page:
    def __init__(self, name: str, display: str):
        self.name, self.display = name, display
        self.visuals: list[dict] = []

    def add(self, vid: str, vtype: str, x: int, y: int, w: int, h: int, roles: dict | None = None, title: str | None = None,
            objects: dict | None = None, container: dict | None = None, sort: tuple[str, str] | None = None,
            sync: str | None = None, drill: bool = False) -> None:
        z = (len(self.visuals) + 1) * 1000
        visual: dict = {"visualType": vtype}
        if roles:
            qs = {}
            for role, specs in roles.items():
                projs = []
                for i, sp in enumerate(specs):
                    projs.append(projection(sp, active=(i == 0) if drill and role in ("Category", "Rows") and len(specs) > 1 else None))
                qs[role] = {"projections": projs}
            visual["query"] = {"queryState": qs}
            if sort:
                kind, ent, prop = F(sort[0])
                visual["query"]["sortDefinition"] = {"sort": [{"field": field(kind, ent, prop), "direction": sort[1]}]}
        if objects:
            visual["objects"] = objects
        vco = {
            "padding": [{"properties": {"top": n(8), "bottom": n(8), "left": n(12), "right": n(12)}}],
        }
        if title is not None:
            vco["title"] = [{"properties": {"show": b(True), "text": s(title), "fontSize": n(12), "fontColor": solid(INK)}}]
        if container:
            vco.update(container)
        visual["visualContainerObjects"] = vco
        if sync:
            visual["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
        visual["drillFilterOtherVisuals"] = True
        self.visuals.append({"$schema": VC, "name": vid, "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
                             "visual": visual})


def header(p: Page, title: str, subtitle: str) -> None:
    p.add(f"{p.name}_hdr", "textbox", 0, 0, 1280, 64, objects={"general": [{"properties": {"paragraphs": [
        {"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontSize": "18pt", "color": WHITE}}]},
        {"textRuns": [{"value": subtitle, "textStyle": {"fontSize": "10pt", "color": "#C3D0E3"}}]},
    ]}}]}, container={"background": [{"properties": {"show": b(True), "color": solid(NAVY), "transparency": n(0)}}],
                      "border": [{"properties": {"show": b(False)}}],
                      "padding": [{"properties": {"top": n(8), "bottom": n(4), "left": n(20), "right": n(20)}}]})


SLICERS = [("Calendar[Year]", "Year"), ("Geography[Region]", "Region"), ("Product[Product Category]", "Category"),
           ("Product[Gender]", "Gender"), ("Sales Method[Sales Method]", "Channel"), ("Retailer[Retailer]", "Retailer")]


def year_filter(year: int) -> dict:
    return {"general": [{"properties": {"filter": {"filter": {
        "Version": 2, "From": [{"Name": "c", "Entity": "Calendar", "Type": 0}],
        "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": "Year"}}],
                                        "Values": [[{"Literal": {"Value": f"{year}L"}}]]}}}]}}}}]}


def slicers(p: Page, y: int = 72, default_year: int | None = 2021) -> None:
    w, gap, x = 200, 8, 16
    for i, (spec, label) in enumerate(SLICERS):
        objs = {"data": [{"properties": {"mode": s("Dropdown")}}],
                "header": [{"properties": {"show": b(True), "fontColor": solid(MUTED), "textSize": n(9)}}]}
        if label == "Year" and default_year:
            objs.update(year_filter(default_year))
        p.add(f"{p.name}_sl{i}", "slicer", x + i * (w + gap), y, w, 52, {"Values": [spec]}, objects=objs,
              container={"title": [{"properties": {"show": b(False)}}]},
              sync=f"sync_{label}" if (label != "Year" or default_year) else "sync_Year_allyears")


def kpi(p: Page, idx: int, x: int, y: int, w: int, value_m: str, label_m: str, color_m: str | None, caption: str) -> None:
    p.add(f"{p.name}_k{idx}", "card", x, y, w, 70, {"Values": [f"m:{value_m}"]},
          objects={"labels": [{"properties": {"fontSize": n(24), "color": solid(NAVY)}}],
                   "categoryLabels": [{"properties": {"show": b(True), "fontSize": n(10), "color": solid(MUTED)}}]},
          container={"title": [{"properties": {"show": b(False)}}],
                     "padding": [{"properties": {"top": n(6), "bottom": n(0), "left": n(12), "right": n(12)}}]})
    p.add(f"{p.name}_k{idx}t", "card", x, y + 70, w, 30, {"Values": [f"m:{label_m}"]},
          objects={"labels": [{"properties": {"fontSize": n(9), **({"color": measure_color(color_m)} if color_m else {"color": solid(MUTED)})}}],
                   "categoryLabels": [{"properties": {"show": b(False)}}]},
          container={"title": [{"properties": {"show": b(False)}}],
                     "padding": [{"properties": {"top": n(0), "bottom": n(4), "left": n(12), "right": n(12)}}]})
    _ = caption


def note(p: Page, vid: str, x: int, y: int, w: int, h: int, title: str, lines: list[str]) -> None:
    paras = [{"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontSize": "11pt", "color": INK}}]}]
    for ln in lines:
        paras.append({"textRuns": [{"value": ln, "textStyle": {"fontSize": "10pt", "color": "#4E5B70"}}]})
    p.add(vid, "textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": paras}}]},
          container={"padding": [{"properties": {"top": n(10), "bottom": n(10), "left": n(14), "right": n(14)}}]})


def labels_on() -> dict:
    return {"labels": [{"properties": {"show": b(True), "fontSize": n(9)}}]}


def series_color(measure: str, hex_color: str) -> dict:
    return {"properties": {"fill": solid(hex_color)}, "selector": {"metadata": f"_Measures.{measure}"}}


def build_pages() -> list[Page]:
    pages: list[Page] = []
    ym = "Calendar[Year Month]"

    # 1 ---------------------------------------------------------------- executive overview
    p = Page("p01_executive", "Executive Overview")
    header(p, "Executive overview", "Adidas US sales. KPIs compare the selected year with the prior year. Use the slicers to filter every page.")
    slicers(p)
    cards = [("Total Revenue", "Revenue vs PY", "Revenue Color"), ("Operating Profit", "Profit vs PY", "Profit Color"),
             ("Operating Margin", "Margin vs PY", "Margin Color"), ("Revenue YoY %", "Growth Label", None),
             ("Units Sold", "Units vs PY", "Units Color"), ("Transactions", "Transactions vs PY", "Transactions Color"),
             ("Avg Transaction Value", "ATV vs PY", "ATV Color"), ("Active Retailers", "Retailers vs PY", "Retailers Color")]
    for i, (v, lbl, col) in enumerate(cards):
        kpi(p, i, 16 + (i % 4) * 314, 136 + (i // 4) * 108, 306, v, lbl, col, v)
    p.add("p01_trend", "lineChart", 16, 356, 760, 348, {"Category": [ym], "Y": ["m:Total Revenue", "m:Revenue PY"]},
          "Revenue by month, current vs prior year", objects={
              "dataPoint": [series_color("Total Revenue", "#2A78D6"), series_color("Revenue PY", "#9AA7BB")],
              "legend": [{"properties": {"show": b(True), "position": s("Top")}}]}, sort=(ym, "Ascending"))
    p.add("p01_channel", "donutChart", 788, 356, 476, 168, {"Category": ["Sales Method[Sales Method]"], "Y": ["m:Total Revenue"]},
          "Revenue by sales channel", objects={"legend": [{"properties": {"show": b(True), "position": s("Right")}}],
                                               "labels": [{"properties": {"show": b(True), "labelStyle": s("Percent of total")}}]})
    p.add("p01_region", "clusteredBarChart", 788, 536, 476, 168, {"Category": ["Geography[Region]"], "Y": ["m:Total Revenue"]},
          "Revenue by region", objects=labels_on(), sort=("m:Total Revenue", "Descending"))
    pages.append(p)

    # 2 ---------------------------------------------------------------- performance
    p = Page("p02_performance", "Performance")
    header(p, "Business performance", "Monthly, quarterly and annual results, growth and profitability.")
    slicers(p)
    p.add("p02_rev", "clusteredColumnChart", 16, 136, 620, 270, {"Category": [ym], "Y": ["m:Total Revenue"]},
          "Revenue by month", sort=(ym, "Ascending"))
    p.add("p02_margin", "lineChart", 648, 136, 616, 270, {"Category": [ym], "Y": ["m:Operating Margin", "m:Margin PY"]},
          "Operating margin by month, current vs prior year",
          objects={"dataPoint": [series_color("Operating Margin", "#2A78D6"), series_color("Margin PY", "#9AA7BB")],
                   "legend": [{"properties": {"show": b(True), "position": s("Top")}}]}, sort=(ym, "Ascending"))
    p.add("p02_growth", "clusteredColumnChart", 16, 418, 400, 286, {"Category": [ym], "Y": ["m:Revenue YoY %"]},
          "Revenue growth vs same month last year", sort=(ym, "Ascending"))
    p.add("p02_ytd", "areaChart", 428, 418, 420, 286, {"Category": [ym], "Y": ["m:Revenue YTD", "m:Revenue PY YTD"]},
          "Cumulative revenue (year to date)",
          objects={"dataPoint": [series_color("Revenue YTD", "#2A78D6"), series_color("Revenue PY YTD", "#9AA7BB")],
                   "legend": [{"properties": {"show": b(True), "position": s("Top")}}]}, sort=(ym, "Ascending"))
    p.add("p02_matrix", "pivotTable", 860, 418, 404, 286,
          {"Rows": ["Calendar[Year]", "Calendar[Quarter]"], "Values": ["m:Total Revenue", "m:Operating Profit", "m:Operating Margin", "m:Revenue YoY %"]},
          "Annual and quarterly summary")
    pages.append(p)

    # 3 ---------------------------------------------------------------- products
    p = Page("p03_products", "Product Analytics")
    header(p, "Product and category analytics", "Best and worst sellers, category contribution, profitability and trends.")
    slicers(p)
    p.add("p03_rank", "clusteredBarChart", 16, 136, 500, 270, {"Category": ["Product[Product]"], "Y": ["m:Total Revenue"]},
          "Revenue by product (best to worst)", objects=labels_on(), sort=("m:Total Revenue", "Descending"))
    p.add("p03_cat", "donutChart", 528, 136, 360, 270, {"Category": ["Product[Product Category]"], "Y": ["m:Total Revenue"]},
          "Category contribution", objects={"legend": [{"properties": {"show": b(True), "position": s("Bottom")}}]})
    p.add("p03_type", "clusteredBarChart", 900, 136, 364, 270, {"Category": ["Product[Product Type]"], "Y": ["m:Operating Margin"]},
          "Operating margin by product type", objects=labels_on(), sort=("m:Operating Margin", "Descending"))
    p.add("p03_scatter", "scatterChart", 16, 418, 500, 286,
          {"Category": ["Product[Product]"], "X": ["m:Total Revenue"], "Y": ["m:Operating Margin"], "Size": ["m:Units Sold"]},
          "Product profitability: revenue vs margin (bubble = units)",
          objects={"categoryLabels": [{"properties": {"show": b(True)}}]})
    p.add("p03_trend", "lineChart", 528, 418, 736, 286, {"Category": [ym], "Y": ["m:Total Revenue"], "Series": ["Product[Product]"]},
          "Product revenue trend by month", objects={"legend": [{"properties": {"show": b(True), "position": s("Top")}}]},
          sort=(ym, "Ascending"))
    pages.append(p)

    # 4 ---------------------------------------------------------------- regional
    p = Page("p04_regional", "Regional Analytics")
    header(p, "Regional analytics", "Region, state and city performance. The region chart drills down to state and city.")
    slicers(p)
    p.add("p04_region", "clusteredBarChart", 16, 136, 400, 270,
          {"Category": ["Geography[Region]", "Geography[State]", "Geography[City]"], "Y": ["m:Total Revenue"]},
          "Revenue by region (drill down to state and city)", objects=labels_on(), sort=("m:Total Revenue", "Descending"), drill=True)
    p.add("p04_tree", "treemap", 428, 136, 836, 270, {"Group": ["Geography[State]"], "Values": ["m:Total Revenue"]},
          "Revenue by state")
    p.add("p04_growth", "clusteredColumnChart", 16, 418, 500, 286, {"Category": ["Geography[Region]"], "Y": ["m:Total Revenue", "m:Revenue PY"]},
          "Regional revenue, current vs prior year",
          objects={"dataPoint": [series_color("Total Revenue", "#2A78D6"), series_color("Revenue PY", "#9AA7BB")],
                   "legend": [{"properties": {"show": b(True), "position": s("Top")}}]}, sort=("m:Total Revenue", "Descending"))
    p.add("p04_cities", "tableEx", 528, 418, 736, 286,
          {"Values": ["Geography[City]", "Geography[State]", "Geography[Region]", "m:Total Revenue", "m:Revenue Share", "m:Operating Margin", "m:Revenue YoY %"]},
          "City-wise sales", sort=("m:Total Revenue", "Descending"))
    pages.append(p)

    # 5 ---------------------------------------------------------------- retailers (customers)
    p = Page("p05_retailers", "Customer Analytics")
    header(p, "Customer (retailer) analytics",
           "The data has no individual customers, so each retailer is treated as a customer account. Retailer ID is not unique and is not used.")
    slicers(p)
    p.add("p05_rank", "clusteredBarChart", 16, 136, 420, 270, {"Category": ["Retailer[Retailer]"], "Y": ["m:Total Revenue"]},
          "Revenue by retailer", objects=labels_on(), sort=("m:Total Revenue", "Descending"))
    p.add("p05_mix", "columnChart", 448, 136, 816, 270,
          {"Category": ["Retailer[Retailer]"], "Y": ["m:Total Revenue"], "Series": ["Sales Method[Sales Method]"]},
          "Retailer revenue by sales channel", objects={"legend": [{"properties": {"show": b(True), "position": s("Top")}}]},
          sort=("m:Total Revenue", "Descending"))
    p.add("p05_table", "tableEx", 16, 418, 840, 286,
          {"Values": ["Retailer[Retailer]", "m:Total Revenue", "m:Revenue Share", "m:Operating Profit", "m:Operating Margin",
                      "m:Transactions", "m:Revenue YoY %", "m:First Purchase", "m:Last Purchase"]},
          "Retailer accounts", sort=("m:Total Revenue", "Descending"))
    p.add("p05_gender", "donutChart", 868, 418, 396, 286, {"Category": ["Product[Gender]"], "Y": ["m:Operating Profit"]},
          "Operating profit by gender segment", objects={"legend": [{"properties": {"show": b(True), "position": s("Bottom")}}]})
    pages.append(p)

    # 6 ---------------------------------------------------------------- financial
    p = Page("p06_financial", "Financial Analytics")
    header(p, "Financial analytics",
           "Revenue, implied cost (revenue minus operating profit, as the source has no cost column) and operating profit.")
    slicers(p, default_year=None)
    p.add("p06_bridge", "waterfallChart", 16, 136, 620, 286,
          {"Category": ["Calendar[Year]"], "Breakdown": ["Product[Product]"], "Y": ["m:Operating Profit"]},
          "Operating profit bridge by year, broken down by product")
    p.add("p06_trend", "lineChart", 648, 136, 616, 286, {"Category": [ym], "Y": ["m:Total Revenue", "m:Implied Cost", "m:Operating Profit"]},
          "Revenue, implied cost and operating profit by month",
          objects={"legend": [{"properties": {"show": b(True), "position": s("Top")}}]}, sort=(ym, "Ascending"))
    p.add("p06_marginch", "clusteredBarChart", 16, 434, 400, 270, {"Category": ["Sales Method[Sales Method]"], "Y": ["m:Operating Margin"]},
          "Operating margin by sales channel", objects=labels_on(), sort=("m:Operating Margin", "Descending"))
    p.add("p06_cost", "donutChart", 428, 434, 380, 270, {"Category": ["Product[Product Category]"], "Y": ["m:Implied Cost"]},
          "Implied cost by category", objects={"legend": [{"properties": {"show": b(True), "position": s("Bottom")}}]})
    p.add("p06_pl", "pivotTable", 820, 434, 444, 270,
          {"Rows": ["Product[Product Category]", "Product[Product]"], "Values": ["m:Total Revenue", "m:Implied Cost", "m:Operating Profit", "m:Operating Margin"]},
          "Profit and loss by product")
    pages.append(p)

    # 7 ---------------------------------------------------------------- operations
    p = Page("p07_operations", "Operational Analytics")
    header(p, "Operational analytics", "Order volume, timing patterns and channel efficiency.")
    slicers(p)
    p.add("p07_volume", "clusteredColumnChart", 16, 136, 620, 270, {"Category": [ym], "Y": ["m:Transactions"]},
          "Order volume (transactions) by month", sort=(ym, "Ascending"))
    p.add("p07_channel", "columnChart", 648, 136, 616, 270,
          {"Category": [ym], "Y": ["m:Total Revenue"], "Series": ["Sales Method[Sales Method]"]},
          "Sales contribution by channel", objects={"legend": [{"properties": {"show": b(True), "position": s("Top")}}]},
          sort=(ym, "Ascending"))
    p.add("p07_weekday", "pivotTable", 16, 418, 620, 286,
          {"Rows": ["Calendar[Weekday]"], "Columns": ["Calendar[Month]"], "Values": ["m:Transactions"]},
          "Transactions by weekday and month")
    p.add("p07_eff", "tableEx", 648, 418, 616, 200,
          {"Values": ["Sales Method[Sales Method]", "m:Transactions", "m:Units Sold", "m:Units per Transaction", "m:Revenue per Unit",
                      "m:Operating Margin", "m:Revenue Share"]},
          "Channel efficiency", sort=("m:Total Revenue", "Descending"))
    note(p, "p07_note", 648, 626, 616, 78, "Not available in this dataset",
         ["Order processing time, delivery performance and cancellation rate need ship date, delivery date or order status columns."])
    pages.append(p)

    # 8 ---------------------------------------------------------------- data quality
    p = Page("p08_quality", "Data Quality")
    header(p, "Data quality", "Checks run on the source data. Figures here explain why some numbers need confirming before external use.")
    slicers(p, default_year=None)
    dq_cards = [("Transactions", "Rows in source"), ("Rows Failing Revenue Check", "Rows failing check"),
                ("% Rows Failing Revenue Check", "Share failing"), ("Revenue Gap", "Reported minus price × units")]
    for i, (m, _) in enumerate(dq_cards):
        p.add(f"p08_c{i}", "card", 16 + i * 314, 136, 306, 80, {"Values": [f"m:{m}"]},
              objects={"labels": [{"properties": {"fontSize": n(22), "color": solid(NAVY)}}],
                       "categoryLabels": [{"properties": {"show": b(True), "fontSize": n(10), "color": solid(MUTED)}}]},
              container={"title": [{"properties": {"show": b(False)}}]})
    p.add("p08_cmp", "clusteredColumnChart", 16, 228, 620, 280,
          {"Category": ["Sales Method[Sales Method]"], "Y": ["m:Total Revenue", "m:Revenue (Price × Units)"]},
          "Reported revenue vs price × units, by sales channel",
          objects={"dataPoint": [series_color("Total Revenue", "#2A78D6"), series_color("Revenue (Price × Units)", "#EB6834")],
                   "legend": [{"properties": {"show": b(True), "position": s("Top")}}]})
    p.add("p08_table", "tableEx", 648, 228, 616, 280,
          {"Values": ["Sales[Revenue Check]", "m:Transactions", "m:Total Revenue", "m:Revenue (Price × Units)"]},
          "Revenue consistency check", sort=("m:Transactions", "Descending"))
    note(p, "p08_note", 16, 520, 1248, 184, "Findings", [
        "1. In about 40% of rows (3,886 of 9,648), Total Sales is exactly 10× Price per Unit × Units Sold, including every In-Store row. "
        "Revenue measures use Total Sales as reported; confirm the authoritative definition with the data owner.",
        "2. Retailer ID is not a unique key (the same ID is shared by Foot Locker, Kohl's, Sports Direct and Walmart), so retailers are identified by name.",
        "3. 2021 has 8,346 transactions against 1,302 in 2020. Year-over-year growth may partly reflect how much activity was recorded.",
        "4. Cost is implied as Total Sales minus Operating Profit; there is no cost, budget, order ID, ship date or order status column.",
    ])
    pages.append(p)
    return pages


THEME = {
    "name": "Meridian Navy",
    "dataColors": ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#6250D6", "#E34948"],
    "foreground": INK, "foregroundNeutralSecondary": "#4E5B70", "foregroundNeutralTertiary": MUTED,
    "background": WHITE, "backgroundLight": "#F7F9FB", "backgroundNeutral": LINE, "tableAccent": NAVY,
    "good": "#0B7A3B", "neutral": "#EDA100", "bad": "#B9312A",
    "maximum": "#0D366B", "center": "#6DA7EC", "minimum": "#CDE2FB", "null": "#F1F3F6",
    "hyperlink": "#1C5CAB", "visitedHyperlink": "#1C5CAB",
    "textClasses": {
        "callout": {"fontSize": 24, "fontFace": "Segoe UI Semibold", "color": NAVY},
        "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
        "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
        "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": "#4E5B70"},
    },
    "visualStyles": {
        "*": {"*": {
            "background": [{"show": True, "color": {"solid": {"color": WHITE}}, "transparency": 0}],
            "border": [{"show": True, "color": {"solid": {"color": LINE}}, "radius": 8}],
            "dropShadow": [{"show": False}],
            "visualHeader": [{"show": True}],
        }},
        "page": {"*": {
            "background": [{"color": {"solid": {"color": "#F3F5F8"}}, "transparency": 0}],
            "outspace": [{"color": {"solid": {"color": "#F3F5F8"}}, "transparency": 0}],
        }},
        "tableEx": {"*": {"grid": [{"gridHorizontal": True, "gridHorizontalColor": {"solid": {"color": LINE}}, "gridVertical": False}],
                          "columnHeaders": [{"fontColor": {"solid": {"color": WHITE}}, "backColor": {"solid": {"color": NAVY}}}]}},
        "pivotTable": {"*": {"columnHeaders": [{"fontColor": {"solid": {"color": WHITE}}, "backColor": {"solid": {"color": NAVY}}}],
                             "rowHeaders": [{"fontColor": {"solid": {"color": INK}}}]}},
    },
}


def write_report(root: Path, base_theme_src: Path) -> None:
    rp = root / f"{PROJECT}.Report"
    d = rp / "definition"
    d.mkdir(parents=True, exist_ok=True)
    (rp / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}}}, indent=2))
    (rp / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJECT}, "config": {"version": "2.0", "logicalId": tag("logical", "report")}}, indent=2))
    shared = rp / "StaticResources" / "SharedResources" / "BaseThemes"
    reg = rp / "StaticResources" / "RegisteredResources"
    shared.mkdir(parents=True, exist_ok=True)
    reg.mkdir(parents=True, exist_ok=True)
    shutil.copy(base_theme_src, shared / "CY24SU10.json")
    theme_file = "MeridianNavy.json"
    (reg / theme_file).write_text(json.dumps(THEME, indent=2))
    (d / "version.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"}, indent=2))
    report = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.2.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"},
            "customTheme": {"name": theme_file, "reportVersionAtImport": "5.61", "type": "RegisteredResources"},
        },
        "layoutOptimization": "None",
        "objects": {"outspacePane": [{"properties": {"expanded": b(False)}}]},
        "resourcePackages": [
            {"name": "RegisteredResources", "type": "RegisteredResources", "items": [{"name": theme_file, "path": theme_file, "type": "CustomTheme"}]},
            {"name": "SharedResources", "type": "SharedResources", "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
        ],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    }
    (d / "report.json").write_text(json.dumps(report, indent=2))
    pages = build_pages()
    pdir = d / "pages"
    pdir.mkdir(exist_ok=True)
    (pdir / "pages.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.name for p in pages], "activePageName": pages[0].name}, indent=2))
    for p in pages:
        pd = pdir / p.name
        (pd / "visuals").mkdir(parents=True, exist_ok=True)
        (pd / "page.json").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.3.0/schema.json",
            "name": p.name, "displayName": p.display, "displayOption": "FitToPage", "height": 720, "width": 1280}, indent=2))
        for v in p.visuals:
            vd = pd / "visuals" / v["name"]
            vd.mkdir(parents=True, exist_ok=True)
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False))


def main() -> None:
    out = Path(sys.argv[1])
    excel = sys.argv[2] if len(sys.argv) > 2 else r"C:\Data\Adidas US Sales Datasets.xlsx"
    # Power BI's built-in base theme; defaults to the copy shipped with the report in this repo.
    base_theme = Path(sys.argv[3]) if len(sys.argv) > 3 else (
        Path(__file__).resolve().parent.parent / "Adidas Sales Analytics.Report"
        / "StaticResources" / "SharedResources" / "BaseThemes" / "CY24SU10.json")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / f"{PROJECT}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}], "settings": {"enableAutoRecovery": True}}, indent=2))
    write_model(out, excel)
    write_report(out, base_theme)
    (out / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    print("written", out)


if __name__ == "__main__":
    main()
