// Faux Pro VS Mini pour les tests de Hector the Manager.
// Il remplace navigator.requestMIDIAccess avant le chargement de la page et
// repond aux memes messages SysEx que le vrai synthe (d'apres le code d'Hector).
// Tout est pilotable depuis les tests via window.__synth.
(() => {
  const P = [0xF0, 0x00, 0x20, 0x32, 0x00, 0x01, 0x33];
  const cs = a => (-a.reduce((x, y) => x + y, 0)) & 127;

  function makeProgram(i) {
    const d = new Array(64).fill(0);
    for (let k = 0; k < 55; k++) d[k] = (i * 7 + k * 3) % 128;
    const name = ("PROG" + String(i + 1).padStart(2, "0") + "__").slice(0, 8);
    for (let k = 0; k < 8; k++) d[55 + k] = name.charCodeAt(k);
    d[63] = 0;
    return d;
  }

  const S = window.__synth = {
    listening: true,        // "SysEx Receive Listening" du synthe
    selected: 0,            // programme selectionne (0..31)
    progs: Array.from({ length: 32 }, (_, i) => makeProgram(i)),
    log: [],                // tous les messages recus par le synthe
    writes: 0,              // nombre d'ecritures SysEx recues
    dropReads: false,       // true : ne repond plus aux demandes de lecture
    corruptNextReply: false,// true : le prochain preset ou banque envoye a une mauvaise somme de controle
    invalidSends: 0,        // messages qu'un vrai port Web MIDI aurait refuses
    badChecksums: 0,        // ecritures refusees pour somme de controle fausse
    pats: Array.from({ length: 16 }, (_, i) => Array.from({ length: 128 }, (_, k) => k < 64 ? (i * 5 + k) % 127 : ((k - 64) % 16 < 12 ? 1 : 0))),
    selectedPattern: 0,     // pattern selectionne sur le synthe (0..15)
  };

  const input = {
    id: "in1", name: "PROVS-MINI", manufacturer: "Behringer", type: "input",
    state: "connected", connection: "open", onmidimessage: null,
    addEventListener() {}, removeEventListener() {},
    open() { return Promise.resolve(this); }, close() { return Promise.resolve(this); },
  };

  function reply(bytes) {
    if (S.corruptNextReply && bytes.length > 20) { bytes[bytes.length - 2] ^= 0x01; S.corruptNextReply = false; }
    setTimeout(() => input.onmidimessage && input.onmidimessage({ data: new Uint8Array(bytes), timeStamp: performance.now() }), 15);
  }

  function handle(m) {
    S.log.push(m);
    const status = m[0] & 0xF0;
    if (status === 0xC0) { S.selected = m[1] & 31; return; }
    if (m[0] !== 0xF0 || !P.every((v, i) => m[i] === v)) return;
    const c = m[7];
    if (m.length === 9 && c === 0x08) { reply([...P, 0x09, 0xF7]); return; }          // device query
    if (m.length === 9 && c === 0x75) return;                                        // transfer ready
    if (m.length === 10 && c === 0x00 && m[8] === 0x00) {                            // read active preset
      if (S.dropReads) return;
      const d = S.progs[S.selected];
      reply([...P, 0x17, ...d, 0x00, cs(d), 0xF7]); return;
    }
    if (m.length === 10 && c === 0x00 && m[8] === 0x20) {                            // read full bank
      if (S.dropReads) return;
      const all = S.progs.flat();
      reply([...P, 0x12, ...all, cs(all), 0xF7]); return;
    }
    if (m.length === 75 && c === 0x15) {                                             // write active program
      S.writes++;
      if (m[73] !== cs(m.slice(8, 72))) { S.badChecksums++; return; }
      if (S.listening) S.progs[S.selected] = Array.from(m.slice(8, 72));
      return;
    }
    if (m.length === 10 && c === 0x01 && m[8] === 0x10) {                            // read 16 patterns
      if (S.dropReads) return;
      const all = S.pats.flat();
      reply([...P, 0x20, ...all, cs(all), 0xF7]); return;
    }
    if (m.length === 10 && c === 0x01 && m[8] === 0x00) {                            // read selected pattern
      if (S.dropReads) return;
      const d = S.pats[S.selectedPattern];
      reply([...P, 0x25, ...d, cs(d), 0xF7]); return;
    }
    if ((c === 0x25 && m.length === 138) || (c === 0x20 && m.length === 2058)) {      // write pattern(s)
      S.writes++;
      const payload = m.slice(8, -2);
      if (m[m.length - 2] !== cs(payload)) { S.badChecksums++; return; }
      if (!S.listening) return;
      if (c === 0x25) S.pats[S.selectedPattern] = Array.from(payload);
      else for (let i = 0; i < 16; i++) S.pats[i] = Array.from(payload.slice(i * 128, (i + 1) * 128));
      return;
    }
    if (c === 0x12 && (m.length - 10) % 64 === 0) {                                  // write bank
      S.writes++;
      const payload = m.slice(8, -2);
      if (m[m.length - 2] !== cs(payload)) { S.badChecksums++; return; }
      if (!S.listening) return;
      for (let i = 0; i < payload.length / 64; i++) S.progs[i] = Array.from(payload.slice(i * 64, (i + 1) * 64));
    }
  }

  const output = {
    id: "out1", name: "PROVS-MINI", manufacturer: "Behringer", type: "output",
    state: "connected", connection: "open",
    send(data, t) {
      const m = Array.from(data);
      // Comme un vrai port Web MIDI : un octet de donnees > 127 dans un SysEx est refuse.
      if (m.some(b => b < 0 || b > 255) || (m[0] === 0xF0 && m.slice(1, -1).some(b => b > 127))) {
        S.invalidSends++;
        throw new TypeError("Invalid MIDI message (data byte > 0x7F)");
      }
      const delay = t ? Math.max(0, t - performance.now()) : 0;
      setTimeout(() => handle(m), delay);
    },
    open() { return Promise.resolve(this); }, close() { return Promise.resolve(this); }, clear() {},
  };

  const access = {
    inputs: new Map([["in1", input]]), outputs: new Map([["out1", output]]),
    onstatechange: null, sysexEnabled: true, addEventListener() {}, removeEventListener() {},
  };
  navigator.requestMIDIAccess = () => Promise.resolve(access);
})();
