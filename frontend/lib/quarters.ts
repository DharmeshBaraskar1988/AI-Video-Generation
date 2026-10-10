export type Quarter = {
  id: string;
  video_id: string;
  period: string;
  months: string | null;
  revenue: number | null;
  net_profit: number | null;
  eps_qr: number | null;
  derived: boolean;
  derivation: string | null;
  derived_fields: string[];
  sources: string[];
  is_single_quarter: boolean;
  is_current: boolean;
  is_loss: boolean;
};

export type CompanyQuarters = {
  id: string;
  company: {
    name_en: string;
    name_ar: string;
    ticker: string;
    exchange: string;
    currency: string;
    unit: string;
  };
  current_quarter: string;
  demo: boolean;
  note: string;
  quarters: Quarter[];
};

export type QuartersResponse = {
  companies: CompanyQuarters[];
  errors: { file: string; error: string }[];
};

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** QR million amount for display; losses are shown as a positive amount with a "loss" label. */
export function formatQrMillion(value: number): string {
  return `QR ${nf.format(Math.abs(value))} m`;
}

export function formatEps(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}QR ${Math.abs(value).toFixed(2)}`;
}
