"""Business-field catalogue and source-column mapping.

Uploaded files never share one schema. The user maps their columns onto these
business fields (the UI pre-fills suggestions from this module). Analytics
modules then switch metrics on or off depending on which fields are mapped.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BusinessField:
    key: str
    label: str
    group: str
    dtype: str  # date | number | text
    description: str
    synonyms: tuple[str, ...]
    required: bool = False
    accepts: tuple[str, ...] = field(default=())  # profiler types accepted

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["synonyms"] = list(self.synonyms)
        d["accepts"] = list(self.accepts)
        return d


NUM = ("number", "integer", "currency", "percent")
TXT = ("text", "category", "id", "boolean", "integer")

FIELDS: tuple[BusinessField, ...] = (
    BusinessField("txn_date", "Transaction date", "Time", "date", "Date of the sale, invoice or order. Drives every trend and period comparison.",
                  ("invoice date", "order date", "transaction date", "sale date", "sales date", "date", "txn date", "posting date", "invoice dt", "order dt"),
                  required=True, accepts=("date",)),
    BusinessField("revenue", "Revenue", "Financial", "number", "Sales value of the transaction. Can be derived from unit price × quantity.",
                  ("total sales", "revenue", "sales", "sales amount", "net sales", "gross sales", "amount", "turnover", "sales value", "total revenue", "line total", "total"),
                  required=True, accepts=NUM),
    BusinessField("quantity", "Units / quantity", "Financial", "number", "Number of units sold.",
                  ("units sold", "quantity", "qty", "units", "volume", "quantity sold", "unit sold"), accepts=NUM),
    BusinessField("unit_price", "Unit price", "Financial", "number", "Selling price per unit.",
                  ("price per unit", "unit price", "price", "selling price", "list price", "rate"), accepts=NUM),
    BusinessField("cost", "Cost", "Financial", "number", "Cost of goods / cost of sale.",
                  ("cost", "cogs", "cost of goods sold", "total cost", "cost of sales", "unit cost"), accepts=NUM),
    BusinessField("profit", "Profit", "Financial", "number", "Gross or operating profit per transaction.",
                  ("operating profit", "profit", "gross profit", "gross margin amount", "contribution"), accepts=NUM),
    BusinessField("net_profit", "Net profit", "Financial", "number", "Profit after all expenses.",
                  ("net profit", "net income", "net margin amount"), accepts=NUM),
    BusinessField("margin_pct", "Margin %", "Financial", "number", "Reported margin ratio. Used only to cross-check profit ÷ revenue.",
                  ("operating margin", "margin", "profit margin", "margin %", "margin pct", "gross margin"), accepts=NUM),
    BusinessField("discount", "Discount", "Financial", "number", "Discount amount or rate.", ("discount", "discount amount", "rebate"), accepts=NUM),
    BusinessField("budget", "Budget / target", "Financial", "number", "Planned revenue for budget-versus-actual analysis.",
                  ("budget", "target", "plan", "sales target", "budgeted revenue", "quota"), accepts=NUM),
    BusinessField("order_id", "Order ID", "Order", "text", "Identifier that groups lines into orders (enables true AOV).",
                  ("order id", "invoice id", "invoice number", "order number", "transaction id", "invoice no", "order no", "receipt"), accepts=TXT),
    BusinessField("order_status", "Order status", "Order", "text", "Status such as Completed / Cancelled / Returned (enables cancellation rate).",
                  ("status", "order status", "fulfilment status", "fulfillment status", "delivery status"), accepts=TXT),
    BusinessField("ship_date", "Ship date", "Order", "date", "Date the order shipped (enables processing time).",
                  ("ship date", "shipped date", "dispatch date", "shipping date"), accepts=("date",)),
    BusinessField("delivery_date", "Delivery date", "Order", "date", "Date the order was delivered (enables delivery performance).",
                  ("delivery date", "delivered date", "received date"), accepts=("date",)),
    BusinessField("customer_id", "Customer ID", "Customer", "text", "Unique customer / account identifier.",
                  ("customer id", "client id", "account id", "retailer id", "buyer id", "cust id"), accepts=TXT),
    BusinessField("customer_name", "Customer / account", "Customer", "text", "Customer, client, retailer or account name.",
                  ("customer", "customer name", "client", "account", "retailer", "buyer", "account name", "client name", "retailer name"), accepts=TXT),
    BusinessField("customer_segment", "Customer segment", "Customer", "text", "Segment such as consumer/corporate or a demographic like gender.",
                  ("customer segment", "segment", "gender", "customer type", "demographic", "tier"), accepts=TXT),
    BusinessField("product", "Product", "Product", "text", "Product or item name.",
                  ("product", "product name", "item", "item name", "sku name", "article", "model"), accepts=TXT),
    BusinessField("product_id", "Product ID / SKU", "Product", "text", "Product identifier.", ("product id", "sku", "item id", "product key", "product code"), accepts=TXT),
    BusinessField("category", "Product category", "Product", "text", "Top-level product grouping.", ("product category", "category", "product line", "department"), accepts=TXT),
    BusinessField("subcategory", "Product sub-category", "Product", "text", "Second-level product grouping.",
                  ("product type", "sub category", "subcategory", "sub-category", "type", "class"), accepts=TXT),
    BusinessField("brand", "Brand", "Product", "text", "Brand name.", ("brand", "manufacturer", "label"), accepts=TXT),
    BusinessField("region", "Region", "Geography", "text", "Sales region or territory.", ("region", "territory", "area", "zone", "sales region", "market"), accepts=TXT),
    BusinessField("country", "Country", "Geography", "text", "Country.", ("country", "nation", "country name"), accepts=TXT),
    BusinessField("state", "State / province", "Geography", "text", "State or province.", ("state", "province", "state name", "county"), accepts=TXT),
    BusinessField("city", "City", "Geography", "text", "City or town.", ("city", "town", "city name", "location"), accepts=TXT),
    BusinessField("channel", "Sales channel", "Commercial", "text", "Channel such as online, in-store, outlet, wholesale.",
                  ("sales method", "channel", "sales channel", "method", "order channel", "source", "platform"), accepts=TXT),
    BusinessField("business_unit", "Business unit", "Commercial", "text", "Division, business unit or line of business.",
                  ("business unit", "division", "bu", "line of business", "lob", "segment unit"), accepts=TXT),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _score(column: str, fld: BusinessField) -> float:
    col = _norm(column)
    best = 0.0
    for syn in fld.synonyms:
        s = _norm(syn)
        if col == s:
            return 1.0
        col_tokens, syn_tokens = set(col.split()), set(s.split())
        if syn_tokens and syn_tokens <= col_tokens:
            best = max(best, 0.75 + 0.05 * len(syn_tokens) - 0.03 * len(col_tokens - syn_tokens))
        ratio = difflib.SequenceMatcher(None, col, s).ratio()
        if ratio >= 0.82:
            best = max(best, ratio * 0.8)
    return best


def suggest_mapping(profiles: list[dict[str, Any]], conflicts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Greedy best-match assignment of source columns to business fields.

    Returns {"mapping": {field: column}, "confidence": {field: score}, "warnings": [...]}.
    """
    by_name = {p["name"]: p for p in profiles}
    candidates: list[tuple[float, str, str]] = []
    for fld in FIELDS:
        for col, prof in by_name.items():
            if prof["inferred_type"] == "empty":
                continue
            s = _score(col, fld)
            if s < 0.6:
                continue
            if fld.accepts and prof["inferred_type"] not in fld.accepts:
                if fld.dtype == "text" and prof["inferred_type"] in NUM and s >= 0.95:
                    s *= 0.9  # numeric codes can still be identifiers
                else:
                    continue
            candidates.append((s, fld.key, col))
    candidates.sort(key=lambda t: (-t[0], t[1]))
    mapping: dict[str, str] = {}
    confidence: dict[str, float] = {}
    used: set[str] = set()
    for score, key, col in candidates:
        if key in mapping or col in used:
            continue
        mapping[key] = col
        confidence[key] = round(score, 2)
        used.add(col)

    warnings: list[str] = []
    # An ID column that maps to several names is not a usable customer key.
    for c in conflicts or []:
        if mapping.get("customer_id") == c.get("id_column") and mapping.get("customer_name") == c.get("name_column"):
            mapping.pop("customer_id")
            confidence.pop("customer_id", None)
            warnings.append(
                f"'{c['id_column']}' was not mapped to Customer ID because the same ID is shared by different "
                f"'{c['name_column']}' values ({c['example']}). Customers are identified by name instead."
            )
    if "revenue" not in mapping and {"unit_price", "quantity"} <= mapping.keys():
        warnings.append("No revenue column found: revenue will be derived as unit price × quantity.")
    return {"mapping": mapping, "confidence": confidence, "warnings": warnings}


def validate_mapping(mapping: dict[str, str], columns: list[str], revenue_source: str = "column") -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cols = set(columns)
    for key, col in mapping.items():
        if key not in FIELD_BY_KEY:
            errors.append(f"Unknown business field '{key}'.")
        elif col not in cols:
            errors.append(f"Column '{col}' mapped to {FIELD_BY_KEY[key].label} does not exist in the sheet.")
    used = [c for c in mapping.values()]
    dupes = {c for c in used if used.count(c) > 1}
    for c in dupes:
        warnings.append(f"Column '{c}' is mapped to more than one business field.")
    if "txn_date" not in mapping:
        errors.append("Map a Transaction date column. Every trend and period comparison depends on it.")
    can_derive = {"unit_price", "quantity"} <= mapping.keys()
    if revenue_source == "derived" and not can_derive:
        errors.append("Deriving revenue needs both Unit price and Units / quantity mapped.")
    if "revenue" not in mapping and not can_derive:
        errors.append("Map a Revenue column, or map Unit price and Units / quantity so revenue can be derived.")
    return errors, warnings
