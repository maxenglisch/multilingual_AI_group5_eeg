/* Synthetic EEG emotion dataset generated from the uploaded CSV distribution.
   Import/insert into eeg_zustaende.html after BANDS/TREND, then run STATES.push(...SYNTHETIC_STATES). */
const SYNTHETIC_STATES = [
  {
    "id": "neutral_baseline",
    "label": "Neutral / Baseline",
    "html_state_id": "uebersicht",
    "trigger_code": 200,
    "summary": "Synthetischer Ruhezustand ohne gezielte emotionale Aktivierung; dient als Vergleichsbasis.",
    "mappings": []
  },
  {
    "id": "freude_positive_valenz",
    "label": "Freude / positive Valenz",
    "html_state_id": "valenz",
    "trigger_code": 201,
    "summary": "Positive Annäherung: linksfrontal wird Alpha relativ unterdrückt, rechtsfrontal bleibt Alpha höher. Das erzeugt eine sichtbare frontale Valenz-Asymmetrie.",
    "mappings": [
      {
        "el": "F3",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.88,
        "note": "Linksfrontaler Alpha-Abfall: mehr kortikale Aktivität links, als synthetischer Marker für Annäherung / positive Valenz."
      },
      {
        "el": "AF3",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.82,
        "note": "Ergänzende linksfrontale Ableitung zur Stabilisierung der positiven Valenz-Asymmetrie."
      },
      {
        "el": "F4",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.7,
        "note": "Rechtsfrontal bleibt Alpha relativ höher; Gegenpol zur linksfrontalen Aktivierung."
      },
      {
        "el": "AF4",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.64,
        "note": "Rechtsfrontale Vergleichsableitung für den Asymmetrie-Index."
      }
    ]
  },
  {
    "id": "negative_valenz_rueckzug",
    "label": "Negative Valenz / Rückzug",
    "html_state_id": "valenz",
    "trigger_code": 202,
    "summary": "Negative Rückzugs-Tendenz: rechtsfrontales Alpha wird stärker unterdrückt, linksfrontales Alpha bleibt höher.",
    "mappings": [
      {
        "el": "F4",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.87,
        "note": "Rechtsfrontaler Alpha-Abfall: mehr kortikale Aktivität rechts, als synthetischer Marker für Rückzug / negative Valenz."
      },
      {
        "el": "AF4",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.8,
        "note": "Ergänzende rechtsfrontale Ableitung für die negative Valenz-Asymmetrie."
      },
      {
        "el": "F3",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.69,
        "note": "Linksfrontal bleibt Alpha relativ höher; Gegenpol zur rechtsfrontalen Aktivierung."
      },
      {
        "el": "AF3",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.62,
        "note": "Linksfrontale Vergleichsableitung für den Asymmetrie-Index."
      }
    ]
  },
  {
    "id": "excitement_arousal",
    "label": "Excitement / Arousal",
    "html_state_id": "excitement",
    "trigger_code": 203,
    "summary": "Hohe Erregung: phasischer Anstieg von High-Beta in anterior-frontalen Kanälen. Für Gamma wird bewusst nur ein Nebenwert erzeugt, weil es artefaktanfällig ist.",
    "mappings": [
      {
        "el": "AF3",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.93,
        "note": "Anterior-frontaler High-Beta-Anstieg bei Erregung / Aktivierung."
      },
      {
        "el": "AF4",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.91,
        "note": "Rechts anterior-frontaler High-Beta-Anstieg bei Arousal."
      },
      {
        "el": "F3",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.83,
        "note": "Frontal links: schnelle Aktivierung im High-Beta-Bereich."
      },
      {
        "el": "F4",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.84,
        "note": "Frontal rechts: schnelle Aktivierung im High-Beta-Bereich."
      },
      {
        "el": "Fz",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.74,
        "note": "Frontale Mittellinie als zusätzlicher Arousal-Indikator."
      }
    ]
  },
  {
    "id": "stress_frustration_synth",
    "label": "Stress / Frustration synthetisch",
    "html_state_id": "stress",
    "trigger_code": 204,
    "summary": "Anhaltender Stress: frontozentrales High-Beta steigt deutlich, posteriorer Alpha-Anteil wird im Vergleich zur Ruhe reduziert.",
    "mappings": [
      {
        "el": "Fz",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.95,
        "note": "Dauerhaftes frontales High-Beta als synthetischer Überlastungsmarker."
      },
      {
        "el": "FCz",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.9,
        "note": "Frontozentraler High-Beta-Anstieg bei kognitiver Anspannung."
      },
      {
        "el": "Cz",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.82,
        "note": "Zentraler High-Beta-Anteil bleibt während Stress erhöht."
      },
      {
        "el": "F3",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.83,
        "note": "Linksfrontaler High-Beta-Anstieg bei Frustration."
      },
      {
        "el": "F4",
        "band": "highbeta",
        "trend": "up",
        "intensity": 0.84,
        "note": "Rechtsfrontaler High-Beta-Anstieg bei Frustration."
      },
      {
        "el": "Pz",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.72,
        "note": "Parietaler Alpha-Abfall: weniger Entspannungspausen im Stresszustand."
      },
      {
        "el": "O1",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.62,
        "note": "Okzipitaler Alpha-Anteil wird im Stresszustand reduziert."
      },
      {
        "el": "O2",
        "band": "alpha",
        "trend": "down",
        "intensity": 0.62,
        "note": "Okzipitaler Alpha-Anteil wird im Stresszustand reduziert."
      }
    ]
  },
  {
    "id": "entspannung_ruhe_synth",
    "label": "Entspannung / Ruhe synthetisch",
    "html_state_id": "entspannung",
    "trigger_code": 205,
    "summary": "Entspannte Wachruhe: posteriorer Alpha-Anteil steigt deutlich, besonders okzipital und parietal.",
    "mappings": [
      {
        "el": "O1",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.94,
        "note": "Okzipital links: starker Alpha-Anstieg im Ruhezustand."
      },
      {
        "el": "O2",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.94,
        "note": "Okzipital rechts: starker Alpha-Anstieg im Ruhezustand."
      },
      {
        "el": "POz",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.88,
        "note": "Okzipitoparietaler Alpha-Anstieg."
      },
      {
        "el": "Pz",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.82,
        "note": "Parietaler Alpha-Anstieg bei nachlassender externer Aufmerksamkeit."
      },
      {
        "el": "P3",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.76,
        "note": "Parietal links: Alpha-Anstieg als Ruheindikator."
      },
      {
        "el": "P4",
        "band": "alpha",
        "trend": "up",
        "intensity": 0.76,
        "note": "Parietal rechts: Alpha-Anstieg als Ruheindikator."
      }
    ]
  },
  {
    "id": "fokus_engagement_synth",
    "label": "Fokus / Engagement synthetisch",
    "html_state_id": "konzentration",
    "trigger_code": 206,
    "summary": "Aufgabenfokus: frontaler Midline-Theta und moderater Low-Beta-Anteil steigen, ohne das starke Stress-High-Beta-Muster.",
    "mappings": [
      {
        "el": "Fz",
        "band": "theta",
        "trend": "up",
        "intensity": 0.86,
        "note": "Frontal-Midline-Theta steigt bei fokussierter kognitiver Kontrolle."
      },
      {
        "el": "FCz",
        "band": "theta",
        "trend": "up",
        "intensity": 0.82,
        "note": "Frontozentraler Theta-Anteil stabilisiert den Fokusmarker."
      },
      {
        "el": "Cz",
        "band": "theta",
        "trend": "up",
        "intensity": 0.7,
        "note": "Zentraler Theta-Anteil als ergänzender Fokusindikator."
      },
      {
        "el": "F3",
        "band": "lowbeta",
        "trend": "up",
        "intensity": 0.68,
        "note": "Low-Beta statt High-Beta: aktives Engagement ohne Stressdominanz."
      },
      {
        "el": "F4",
        "band": "lowbeta",
        "trend": "up",
        "intensity": 0.68,
        "note": "Low-Beta statt High-Beta: aktives Engagement ohne Stressdominanz."
      }
    ]
  }
];
