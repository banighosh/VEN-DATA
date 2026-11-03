export type Dimension =
  | 'region' | 'state' | 'city' | 'category' | 'subcategory' | 'product'
  | 'customer_segment' | 'business_unit' | 'channel' | 'customer';

export type Comparison = 'previous_period' | 'previous_year' | 'none';

export interface Filters {
  start_date: string | null;
  end_date: string | null;
  region: string[];
  state: string[];
  city: string[];
  category: string[];
  subcategory: string[];
  product: string[];
  customer_segment: string[];
  business_unit: string[];
  channel: string[];
  customer: string[];
  comparison: Comparison;
}

export type ValueFormat = 'currency' | 'number' | 'percent' | 'pp';

export interface DatasetSummary {
  id: number;
  name: string;
  source_filename: string;
  sheet_name: string | null;
  header_row: number;
  status: string;
  error?: string | null;
  row_count: number;
  valid_row_count: number;
  date_min: string | null;
  date_max: string | null;
  is_default: boolean;
  mapping: Record<string, string>;
  options: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  quality_score: number | null;
  quality_grade: string | null;
}

export interface QualityIssue {
  severity: 'critical' | 'warning' | 'info';
  category: string;
  column: string | null;
  count: number;
  pct: number;
  message: string;
  examples: unknown[];
}

export interface QualityCheck {
  id: string; name: string; status: 'pass' | 'warn' | 'fail' | 'info';
  affected_rows: number; affected_pct: number; detail: string;
}

export interface QualityReport {
  summary: {
    rows: number; columns: number; cells: number; missing_cells: number; missing_pct: number;
    duplicate_rows: number; duplicate_pct: number; invalid_values: number; critical: number; warnings: number; sampled?: boolean;
  };
  dimensions: { completeness: number; uniqueness: number; validity: number; consistency: number };
  score: number;
  grade: string;
  issues: QualityIssue[];
  checks: QualityCheck[];
  key_conflicts: { id_column: string; name_column: string; ids_affected: number; rows_affected: number; example: string }[];
}

export interface ColumnProfile {
  name: string;
  inferred_type: string;
  non_null: number;
  missing: number;
  missing_pct: number;
  unique: number;
  unique_pct: number;
  invalid: number;
  invalid_examples: unknown[];
  samples: unknown[];
  mixed_types: boolean;
  whitespace_issues: number;
  case_variants: string[][];
  outliers: number;
  stats: Record<string, number | string> | null;
  top_values: { value: string; count: number }[] | null;
}

export interface DatasetDetail extends DatasetSummary {
  quality: QualityReport;
  processing: Record<string, any>;
  columns: ColumnProfile[];
}

export interface BusinessField {
  key: string; label: string; group: string; dtype: string; description: string; required: boolean;
  synonyms: string[]; accepts: string[];
}

export interface SheetSummary { name: string; rows: number | null; columns: number | null; header_row: number; empty: boolean }

export interface UploadResult {
  upload_id: string; filename: string; file_type: string; size_bytes: number;
  sheets: SheetSummary[]; recommended_sheet: string | null;
}

export interface SheetAnalysis {
  upload_id: string; filename: string; sheet: string | null; header_row: number; rows: number; total_rows: number | null;
  columns: string[]; sampled: boolean; notes: string[]; profiles: ColumnProfile[]; preview: Record<string, unknown>[];
  quality: QualityReport; suggestion: { mapping: Record<string, string>; confidence: Record<string, number>; warnings: string[] };
  fields: BusinessField[]; elapsed_ms: number;
}

export interface Capabilities {
  fields: Record<string, { label: string; available: boolean; source: string | null; derived: boolean; group: string }>;
  metrics: Record<string, { label: string; available: boolean; missing: string[]; basis?: string; note?: string }>;
  filters: Record<string, { available: boolean; label: string; source: string | null }>;
  customer_label: string | null;
}

export interface FilterOptions {
  date_min: string | null;
  date_max: string | null;
  dimensions: Record<string, { label: string; values: string[]; truncated: boolean }>;
  links: Record<string, { parent: string; map: Record<string, string> }>;
  years?: number[];
  latest_full_year?: number | null;
}

export interface ScopeMeta {
  label: string; start: string | null; end: string | null; comparison_label: string;
  comparison_start: string | null; comparison_end: string | null; has_comparison: boolean;
  rows: number; comparison_rows: number; notes: string[];
}

export interface Kpi {
  key: string; label: string; available: boolean; format: ValueFormat;
  value?: number | null; previous?: number | null; change?: number | null;
  change_type?: 'relative' | 'absolute'; direction?: 'up' | 'down' | 'flat';
  sentiment?: 'positive' | 'negative' | 'neutral';
  sparkline?: { label: string; value: number | null }[];
  note?: string | null; reason?: string; source?: string | null; derived?: boolean;
}

export interface BreakdownRow {
  key: string; revenue: number; transactions: number; profit: number | null; cost?: number | null; units: number | null;
  margin: number | null; share: number | null; aov: number | null;
  prev_revenue?: number; growth?: number | null; prev_profit?: number | null; prev_margin?: number | null;
  margin_change?: number | null; [k: string]: unknown;
}

export interface SeriesPoint {
  period: string; label: string; end?: string; revenue: number | null; profit?: number | null; cost?: number | null;
  margin?: number | null; units?: number | null; transactions: number; aov?: number | null; budget?: number | null;
  no_data?: boolean;
}

export interface Insight {
  id: string; category: string; severity: 'critical' | 'warning' | 'positive' | 'info';
  title: string; observation: string;
  metrics: { label: string; value: number | null; format: ValueFormat }[];
  implication: string; recommendation: string; interpretation_source: 'rule' | 'ai';
  confidence: 'high' | 'medium' | 'low'; drill?: { page?: string; filter?: Partial<Record<Dimension, string[]>> };
  period?: string;
}

export interface Matrix { rows: string[]; cols: string[]; cells: { row: string; col: string; value: number | null }[]; measure?: string }

export interface Pivot { keys: string[]; rows: Record<string, string | number | null>[] }

export interface Unavailable { available: false; reason: string; requires?: string[] }
