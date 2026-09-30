/*
Minimaler Browser-Adapter für EmotivPRO CSV V2 Dummy / echte EmotivPRO CSV V2.
Er liest die 2 Header-Zeilen, validiert Kernspalten und gibt Zeilenobjekte zurück.
*/
export function parseEmotivProCsvV2(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 3) throw new Error("CSV zu kurz: Erwartet Metadatenzeile, Headerzeile und Daten.");
  const metaLine = lines[0];
  if (!metaLine.includes("title:") || !metaLine.includes("sampling rate:")) {
    throw new Error("Keine EmotivPRO-Metadatenzeile gefunden. Erste Zeile muss key:value Paare enthalten.");
  }
  const meta = Object.fromEntries(metaLine.split(",").map(p => p.split(":").map(s => s.trim())).filter(p => p.length >= 2).map(([k, ...rest]) => [k, rest.join(":")]));
  const columns = splitCsvLine(lines[1]);
  const required = ["Timestamp", "EEG.Counter", "EEG.Interpolated", "MOT.AccX", "CQ.Overall", "EQ.SampleRateQuality"];
  for (const col of required) {
    if (!columns.includes(col)) throw new Error(`Pflichtspalte fehlt: ${col}`);
  }
  const powCols = columns.filter(c => c.startsWith("POW."));
  if (powCols.length === 0) throw new Error("Keine Bandleistungs-Spalten POW.<Sensor>.<Band> gefunden.");
  const rows = [];
  for (let i = 2; i < lines.length; i++) {
    const values = splitCsvLine(lines[i]);
    const row = {};
    columns.forEach((c, j) => row[c] = values[j] ?? "");
    rows.push(row);
  }
  return { meta, columns, rows };
}

function splitCsvLine(line) {
  // reicht für numerische Demo-CSV ohne eingebettete Kommas in Quotes
  return line.split(",");
}

export function getBandpowerIntensity(row, sensor, band) {
  const key = `POW.${sensor}.${band}`;
  if (!(key in row)) throw new Error(`Bandpower fehlt: ${key}`);
  const value = Number(row[key]);
  if (!Number.isFinite(value)) return null;
  return value;
}

export function qualityGate(row) {
  const cq = Number(row["CQ.Overall"]);
  const srq = Number(row["EQ.SampleRateQuality"]);
  if (Number.isFinite(srq) && srq === -1) return { ok: false, reason: "sample_rate_loss" };
  if (Number.isFinite(cq) && cq < 60) return { ok: false, reason: "bad_contact_quality" };
  return { ok: true, reason: "ok" };
}
