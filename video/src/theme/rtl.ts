const EASTERN = "٠١٢٣٤٥٦٧٨٩";

/** Western digits by default; Arabic-Indic when the admin setting says "eastern". */
export const localizeDigits = (text: string, digits: "western" | "eastern"): string =>
  digits === "eastern" ? text.replace(/[0-9]/g, (d) => EASTERN[Number(d)]).replace(/(\d)\.(\d)/g, "$1٫$2") : text;

/** In right-to-left layouts, sequences that read in time order (charts) run right to left. */
export const inReadingOrder = <T,>(items: T[], dir: "ltr" | "rtl"): T[] => (dir === "rtl" ? [...items].reverse() : items);
