import { useCallback, useEffect, useRef, useState } from "react";

/* Specimen pairs cycled in the header strip: real-looking PII -> its fake. */
const SPECIMENS = [
  ["Rashi Patil", "Gregory Mueller"],
  ["rashhi.patil@gmail.com", "david.reynolds@example.com"],
  ["+91 98765 43210", "+91 92037 52864"],
  ["4111 1111 1111 1111", "6565 4105 9472 9449"],
  ["11/3 Village Birdewadi, Pune", "211 Troy Junctions, Bergerside"],
];

const PHASE_MS = { shown: 1500, covering: 550, swapped: 1900 };

function SpecimenStrip() {
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState("shown"); // shown -> covering -> swapped
  const reduced = useRef(
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    if (reduced.current) return undefined;
    const next = { shown: "covering", covering: "swapped", swapped: "shown" }[phase];
    const timer = setTimeout(() => {
      if (phase === "swapped") setIndex((i) => (i + 1) % SPECIMENS.length);
      setPhase(next);
    }, PHASE_MS[phase]);
    return () => clearTimeout(timer);
  }, [phase]);

  const [original, fake] = SPECIMENS[index];
  if (reduced.current) {
    return (
      <p className="specimen" aria-hidden="true">
        <span className="specimen-label">specimen</span>
        <s>{original}</s> <span className="specimen-fake">{fake}</span>
      </p>
    );
  }
  return (
    <p className="specimen" aria-hidden="true">
      <span className="specimen-label">specimen</span>
      <span className={`specimen-token ${phase}`}>
        <span className="specimen-original">{original}</span>
        <span className="specimen-bar" />
        <span className="specimen-fake">{fake}</span>
      </span>
    </p>
  );
}

function formatBytes(n) {
  return n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`;
}

function download(name, text, mime) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: mime }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function MappingRow({ original, fake }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <tr>
      <td>
        <button
          type="button"
          className={`peek ${revealed ? "revealed" : ""}`}
          onClick={() => setRevealed((r) => !r)}
          title={revealed ? "Hide original" : "Reveal original"}
        >
          <span className="peek-text">{original}</span>
        </button>
      </td>
      <td className="arrow" aria-hidden="true">→</td>
      <td className="fake">{fake}</td>
    </tr>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [useNer, setUseNer] = useState(true);
  const [state, setState] = useState("idle"); // idle | running | done | error
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const pick = useCallback((f) => {
    if (!f) return;
    const ok = /\.(pdf|txt)$/i.test(f.name);
    setError(ok ? "" : "Only .pdf and .txt files are supported.");
    setState(ok ? "idle" : "error");
    if (ok) setFile(f);
  }, []);

  async function run() {
    const form = new FormData();
    form.append("file", file);
    setState("running");
    setError("");
    try {
      const res = await fetch(`/api/redact?use_ner=${useNer}`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || res.statusText);
      }
      setResult(await res.json());
      setState("done");
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  }

  const maxCount = result
    ? Math.max(...Object.values(result.by_type))
    : 1;
  const mappingPairs = result
    ? Object.entries(result.mapping).slice(0, 8)
    : [];

  return (
    <div className="page">
      <header className="folder-tab">
        <div className="tab-title">
          <h1>PII Redaction Tool</h1>
          <div className="stamps">
            <span className="stamp">nothing stored</span>
            <span className="stamp">12 PII types</span>
          </div>
        </div>
        <SpecimenStrip />
      </header>

      <main>
        <section className="tray" aria-label="Upload document">
          <label
            className={`dropzone ${dragOver ? "over" : ""} ${file ? "filled" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              pick(e.dataTransfer.files[0]);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt"
              onChange={(e) => pick(e.target.files[0])}
            />
            {file ? (
              <>
                <span className="file-name">{file.name}</span>
                <span className="file-size">{formatBytes(file.size)}</span>
              </>
            ) : (
              <>
                <span className="drop-title">Drop a document in the tray</span>
                <span className="drop-sub">.pdf or .txt — or click to choose</span>
              </>
            )}
          </label>

          <div className="controls">
            <button
              type="button"
              className="primary"
              disabled={!file || state === "running"}
              onClick={run}
            >
              {state === "running" ? "Redacting…" : "Redact document"}
            </button>
            <label className="toggle">
              <input
                type="checkbox"
                checked={useNer}
                onChange={(e) => setUseNer(e.target.checked)}
              />
              Detect names &amp; companies (NER — slower, far better recall)
            </label>
          </div>

          {state === "running" && (
            <p className="status" role="status">
              <span className="bar-loader" aria-hidden="true" />
              Reading, detecting and replacing — a long document takes up to a minute.
            </p>
          )}
          {state === "error" && (
            <p className="status error" role="alert">{error}</p>
          )}
        </section>

        {state === "done" && result && (
          <section className="dossier" aria-label="Redaction results">
            <div className="dossier-head">
              <h2>Redaction report</h2>
              <span className="doc-name">{result.filename}</span>
            </div>

            <dl className="stats">
              <div><dt>redactions</dt><dd>{result.redactions.toLocaleString()}</dd></div>
              <div><dt>unique values</dt><dd>{result.unique_values.toLocaleString()}</dd></div>
              <div><dt>characters</dt><dd>{result.characters.toLocaleString()}</dd></div>
              <div className={result.residual_leftovers ? "flagged" : "cleared"}>
                <dt>residual leftovers</dt><dd>{result.residual_leftovers}</dd>
              </div>
            </dl>

            <ul className="type-bars">
              {Object.entries(result.by_type).map(([type, count]) => (
                <li key={type}>
                  <span className="type-name">{type}</span>
                  <span className="type-track">
                    <span
                      className="type-ink"
                      style={{ width: `${Math.max(2, (count / maxCount) * 100)}%` }}
                    />
                  </span>
                  <span className="type-count">{count.toLocaleString()}</span>
                </li>
              ))}
            </ul>

            {mappingPairs.length > 0 && (
              <div className="mapping">
                <h3>Sample of the mapping <span>click a bar to reveal the original</span></h3>
                <table>
                  <tbody>
                    {mappingPairs.map(([orig, fake]) => (
                      <MappingRow key={orig} original={orig} fake={fake} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="downloads">
              <button
                type="button"
                className="primary"
                onClick={() =>
                  download(
                    (result.filename || "document").replace(/\.\w+$/, "") + ".redacted.txt",
                    result.redacted_text,
                    "text/plain"
                  )
                }
              >
                Download redacted text
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() =>
                  download("pii_mapping.json", JSON.stringify(result.mapping, null, 2), "application/json")
                }
              >
                Download mapping (JSON)
              </button>
            </div>
          </section>
        )}
      </main>

      <footer>
        Processed in memory only — the document and its mapping never touch the server's disk.
      </footer>
    </div>
  );
}
