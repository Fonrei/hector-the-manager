"""Tests automatiques de Hector the Manager.

Trois familles :
  1. Le fichier lui-meme (empreinte CSP, versions, chargement sans erreur).
  2. Les formats SysEx et les imports (sans synthe).
  3. Les echanges avec le synthe (avec le faux Pro VS Mini de fake_synth.js).
"""
import base64
import hashlib
import re
import pytest

PREFIX = [0xF0, 0x00, 0x20, 0x32, 0x00, 0x01, 0x33]


def checksum(data):
    return (-sum(data)) & 127


def preset_payload(seed=1, name="TESTPRE_"):
    d = [(seed * 5 + i * 11) % 128 for i in range(55)] + [ord(c) for c in name[:8].ljust(8, "_")] + [0]
    assert len(d) == 64
    return d


# ---------------------------------------------------------------- 1. Le fichier

def test_csp_hash_matches_script(hector_path):
    """Sans ca, le navigateur bloque tout le script et la page est morte."""
    html = hector_path.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 1, "Un seul bloc <script> attendu"
    expected = base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode()
    found = re.search(r"script-src 'sha256-([^']+)'", html)
    assert found, "Ligne CSP introuvable"
    assert found.group(1) == expected, "Empreinte CSP perimee : lance update_csp.py"


def test_csp_blocks_network(hector_path):
    html = hector_path.read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "connect-src 'none'" in csp
    assert "default-src 'none'" in csp


def test_version_is_consistent(hector_path):
    html = hector_path.read_text(encoding="utf-8")
    versions = {
        "title": re.search(r"<title>Hector the Manager v([\d.]+)</title>", html).group(1),
        "APP_VERSION": re.search(r'const APP_VERSION="([\d.]+)"', html).group(1),
        "footer": re.search(r"· version ([\d.]+) ·", html).group(1),
        "header": re.search(r'id="appVersion">v([\d.]+) ', html).group(1),
        "about": re.search(r"<dt>Version</dt><dd>([\d.]+) ·", html).group(1),
        "banner": re.search(r"/\*! Hector the Manager v([\d.]+) ", html).group(1),
    }
    assert len(set(versions.values())) == 1, f"Numeros de version differents : {versions}"


def test_page_loads_without_errors(hector):
    hector.wait(1000)
    assert hector.errors == []
    assert hector.js("document.querySelectorAll('button').length") > 100


def test_idle_page_is_quiet(hector):
    """Au repos, la page ne doit presque rien consommer (mesure : ~10 ms sur 10 s)."""
    cdp = hector.page.context.new_cdp_session(hector.page)
    cdp.send("Performance.enable")
    get = lambda: {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
    hector.wait(1000)
    a = get()
    hector.wait(5000)
    b = get()
    assert (b["ScriptDuration"] - a["ScriptDuration"]) < 0.25, "Plus de 250 ms de calcul en 5 s de repos"


# ------------------------------------------------- 2. Formats SysEx et imports

def test_single_preset_frame(hector):
    d = preset_payload()
    out = hector.js("d=>Array.from(makeSingle(new Uint8Array(d)))", d)
    assert len(out) == 75
    assert out[:8] == PREFIX + [0x10]
    assert out[8:72] == d
    assert out[72] == 0 and out[73] == checksum(d) and out[74] == 0xF7


def test_active_transfer_frame(hector):
    d = preset_payload()
    out = hector.js("d=>Array.from(makeActiveTransfer(new Uint8Array(d)))", d)
    assert out[:8] == PREFIX + [0x15] and out[73] == checksum(d) and out[74] == 0xF7


def test_preset_file_roundtrip(hector):
    d = preset_payload(3, "ROUNDTR_")
    res = hector.js("d=>{const p=decodePreset(makeSingle(new Uint8Array(d)),'x');return {data:Array.from(p.data),name:p.name}}", d)
    assert res["data"] == d
    assert res["name"] == "ROUNDTR_"


def test_single_patch_bank_bad_checksum_rejected(hector):
    d = preset_payload()
    frame = PREFIX + [0x12] + d + [(checksum(d) + 1) & 127, 0xF7]
    err = hector.js("f=>{try{decodePreset(new Uint8Array(f),'x');return null}catch(e){return e.message}}", frame)
    assert err and "checksum" in err.lower()


def test_preset_file_bad_checksum_rejected(hector):
    """Corrige en v1.9.4."""
    d = preset_payload()
    frame = PREFIX + [0x10] + d + [0x00, (checksum(d) + 1) & 127, 0xF7]
    err = hector.js("f=>{try{decodePreset(new Uint8Array(f),'x');return null}catch(e){return e.message}}", frame)
    assert err, "Un fichier preset corrompu a ete accepte"


def test_preset_file_8bit_byte_rejected(hector):
    """Corrige en v1.9.4."""
    d = preset_payload()
    d[10] = 200
    frame = PREFIX + [0x10] + d + [0x00, checksum(d), 0xF7]
    err = hector.js("f=>{try{decodePreset(new Uint8Array(f),'x');return null}catch(e){return e.message}}", frame)
    assert err, "Un octet > 127 a ete accepte dans un preset"


def test_preset_file_import_valid_and_damaged(hector, tmp_path):
    d = preset_payload(5, "FILEOK__")
    good = tmp_path / "good.syx"
    good.write_bytes(bytes(PREFIX + [0x10] + d + [0x00, checksum(d), 0xF7]))
    bad = tmp_path / "bad.syx"
    bad.write_bytes(bytes(PREFIX + [0x10] + d + [0x00, (checksum(d) + 3) & 127, 0xF7]))
    before = hector.js("items.length")
    for f in (good, bad):
        hector.js("""async b64=>{const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
            await addFiles([new File([bin],'%s')])}""".replace('%s', f.name), __import__('base64').b64encode(f.read_bytes()).decode())
    names = hector.js("items.map(i=>i.name)")
    assert "FILEOK__" in names
    assert hector.js("items.length") == before + 1, "Le fichier abime a ete importe"


def _bank_file(n=4, corrupt=False):
    payload = []
    for i in range(n):
        payload += preset_payload(i, f"BANK{i:02d}__")
    cs = checksum(payload)
    if corrupt:
        cs = (cs + 1) & 127
    return bytes(PREFIX + [0x12] + payload + [cs, 0xF7])


def test_bank_file_import(hector, tmp_path):
    f = tmp_path / "bank.syx"
    f.write_bytes(_bank_file(4))
    before = hector.js("items.length")
    hector.page.set_input_files("#bankFile", str(f))
    hector.until(f"items.length==={before + 4}", timeout=3000)
    names = hector.js("items.slice(-4).map(i=>i.name)")
    assert names == ["BANK00__", "BANK01__", "BANK02__", "BANK03__"]


def test_bank_file_bad_checksum_rejected(hector, tmp_path):
    f = tmp_path / "bad.syx"
    f.write_bytes(_bank_file(4, corrupt=True))
    before = hector.js("items.length")
    hector.page.set_input_files("#bankFile", str(f))
    hector.until("window.__alerts.length>0", timeout=3000)
    assert "checksum" in hector.alerts()[-1].lower()
    assert hector.js("items.length") == before


def test_bank_export_frame(hector):
    d1, d2 = preset_payload(1, "ONE_____"), preset_payload(2, "TWO_____")
    out = hector.js("""([a,b])=>{items=[{data:new Uint8Array(a),name:'ONE',rank:1},{data:new Uint8Array(b),name:'TWO',rank:2}];
        bank=[0,1];return Array.from(makeBank())}""", [d1, d2])
    assert out[:8] == PREFIX + [0x12]
    assert out[8:-2] == d1 + d2
    assert out[-2] == checksum(d1 + d2) and out[-1] == 0xF7


def test_pattern_message_frame(hector):
    data = [i % 128 for i in range(128)]
    out = hector.js("d=>Array.from(makePatternMessage(PATTERN_SINGLE_CMD,new Uint8Array(d)))", data)
    assert out[:8] == PREFIX + [0x25] and out[8:-2] == data
    assert out[-2] == checksum(data) and out[-1] == 0xF7
    err = hector.js("()=>{try{makePatternMessage(PATTERN_SINGLE_CMD,new Uint8Array(127));return null}catch(e){return e.message}}")
    assert err


@pytest.mark.parametrize("bad", ["byte200", "short", "float", "negative"])
def test_pattern_data_validation(hector, bad):
    """Corrige en v1.9.1 : un octet de pattern doit tenir sur 7 bits."""
    data = {"byte200": [200] * 128, "short": [0] * 127, "float": [1.5] * 128, "negative": [-1] * 128}[bad]
    err = hector.js("d=>{try{vp2NormalizeData(d);return null}catch(e){return e.message}}", data)
    assert err, f"Donnees de pattern invalides acceptees ({bad})"


def test_backup_validation(hector):
    ok = hector.js("()=>{try{vp2Validate(vp2DefaultState());return true}catch(e){return e.message}}")
    assert ok is True
    cases = {
        "15 slots": "s.synthBank.pop()",
        "mauvais id": "s.library.push({id:'x',name:'A',origin:'created',data:Array(128).fill(0)})",
        "nom vide": "s.library.push({id:'p-abc-abcdefg',name:' ',origin:'created',data:Array(128).fill(0)})",
        "slot vers pattern absent": "s.synthBank[0].assignedPatternId='p-abc-abcdefg'",
        "octet > 127": "s.library.push({id:'p-abc-abcdefg',name:'A',origin:'created',data:Array(128).fill(130)})",
    }
    for label, mutate in cases.items():
        err = hector.js(f"()=>{{const s=vp2DefaultState();{mutate};try{{vp2Validate(s);return null}}catch(e){{return e.message}}}}")
        assert err, f"Sauvegarde invalide acceptee : {label}"


# ------------------------------------------------------- 3. Avec le faux synthe

def test_connect_selects_provs_ports(hector):
    hector.connect(check=False)
    assert hector.js("midiOut.name") == "PROVS-MINI"
    assert hector.js("midiIn.name") == "PROVS-MINI"


def test_synth_check_listening_on(hector):
    before = hector.synth("S.progs.map(p=>p.slice())")
    hector.connect()
    assert hector.js("vpSynthCheck.listening") is True
    assert hector.synth("S.progs") == before, "La verification a laisse une trace sur le synthe"
    assert hector.errors == []


def test_synth_check_listening_off(hector):
    hector.js("window.__synth.listening=false")
    before = hector.synth("S.progs.map(p=>p.slice())")
    hector.connect()
    assert hector.js("vpSynthCheck.listening") is False
    assert hector.synth("S.progs") == before
    assert hector.js("vpSendAllowed()") is False, "Les envois doivent etre bloques si le synthe n'ecoute pas"


def test_synth_check_interrupted_warns(hector):
    """Corrige en v1.9.2 : si la verification s'interrompt apres son ecriture de test, on previent."""
    hector.connect(check=False)
    hector.js("""()=>{const S=window.__synth,w=S.writes;
       const iv=setInterval(()=>{if(S.writes>w){S.dropReads=true;clearInterval(iv)}},2)}""")
    hector.js("vpCheckSynth()")
    hector.until("!vpSynthCheck.running", timeout=20000)
    assert any("may not have been undone" in a for a in hector.alerts())


def test_write_single_preset_verified(hector):
    hector.connect()
    d = preset_payload(9, "WRITTEN_")
    hector.js("d=>{window.__it={rank:3,name:'W',data:new Uint8Array(d)};sendPresetDataToSynth(window.__it,window.__it.data)}", d)
    hector.idle()
    assert hector.synth("S.badChecksums") == 0, "Le synthe a refuse l'ecriture : somme de controle fausse"
    assert hector.synth("S.progs[2]") == d
    assert "written and checked" in hector.status()
    assert hector.alerts() == []


def test_write_single_preset_ignored_is_reported(hector):
    """Corrige en v1.9.2 : un preset ignore par le synthe ne doit pas rester 'synchronise'."""
    hector.connect()
    hector.js("window.__synth.listening=false")
    original = hector.synth("S.progs[4].slice()")
    d = preset_payload(4, "IGNORED_")
    hector.js("d=>{window.__it={rank:5,name:'I',data:new Uint8Array(d)};sendPresetDataToSynth(window.__it,window.__it.data)}", d)
    hector.idle()
    assert hector.synth("S.progs[4]") == original
    assert hector.js("Array.from(window.__it.synthData)") == original, "Hector croit le preset synchronise"
    assert any("was not taken by the synth" in a for a in hector.alerts())


def test_read_active_preset(hector):
    hector.connect()
    hector.js("window.__synth.selected=6")
    before = hector.js("items.length")
    hector.page.click("#receivePreset")
    hector.until(f"items.length==={before + 1}", timeout=8000)
    item = hector.js("(()=>{const it=items.find(i=>i.name==='PROG07__');return it?Array.from(it.data):null})()")
    assert item == hector.synth("S.progs[6]")


def test_read_active_preset_bad_checksum_rejected(hector):
    hector.connect()
    hector.js("window.__synth.corruptNextReply=true")
    before = hector.js("items.length")
    hector.page.click("#receivePreset")
    hector.until("window.__alerts.length>0", timeout=8000)
    assert "checksum" in hector.alerts()[-1].lower()
    assert hector.js("items.length") == before, "Un preset corrompu a ete importe"


def test_read_full_bank(hector):
    hector.connect()
    hector.page.click("#receiveBank")
    hector.until("bank.length===32", timeout=8000)
    got = hector.js("[...bank].sort((a,b)=>items[a].rank-items[b].rank).map(i=>Array.from(items[i].data))")
    assert got == hector.synth("S.progs")


def test_send_full_bank(hector):
    hector.connect()
    hector.page.click("#receiveBank")
    hector.until("bank.length===32", timeout=8000)
    hector.idle()
    # On modifie le preset 1 localement puis on renvoie la banque entiere.
    hector.js("(()=>{const it=items[bank.find(i=>items[i].rank===1)];it.data=new Uint8Array(it.data);it.data[0]=99})()")
    hector.js("window.__synth.writes=0")
    hector.page.click("#sendBank")
    hector.until("window.__synth.writes>0", timeout=5000)
    hector.wait(200)
    assert hector.synth("S.badChecksums") == 0, "Le synthe a refuse la banque : somme de controle fausse"
    assert hector.synth("S.progs[0][0]") == 99
    assert hector.synth("S.invalidSends") == 0


def test_stop_releases_every_note(hector):
    """Apres Stop, chaque note demarree par le sequenceur doit avoir recu son Note Off."""
    hector.connect()
    data = [60] * 16 + [64] * 16 + [127] * 32 + [1] * 16 + [0] * 48
    hector.js("""d=>{const p=vp2CreatePattern('Stop test',d);vp2State.library.push(p);vp2Open(p.id);
                 livePlaybackMode='synth';window.__synth.log=[];vpGlobalPlay()}""", data)
    hector.wait(1500)
    played = hector.synth("S.log.filter(m=>(m[0]&0xF0)===0x90&&m[2]>0).length")
    assert played > 0, "Le sequenceur n'a joue aucune note"
    hector.js("vpGlobalStop()")
    hector.wait(500)
    balance = hector.synth("""(()=>{const n={};for(const m of S.log){const t=m[0]&0xF0;
        if(t===0x90&&m[2]>0)n[m[1]]=(n[m[1]]||0)+1;
        else if(t===0x80||(t===0x90&&m[2]===0))n[m[1]]=(n[m[1]]||0)-1}
        return Object.entries(n).filter(([k,v])=>v>0).map(([k])=>Number(k))})()""")
    assert balance == [], f"Notes restees enfoncees apres Stop : {balance}"


def test_no_invalid_midi_ever_sent(hector):
    """Garde-fou general : apres un scenario complet, aucun message refuse par Web MIDI."""
    hector.connect()
    hector.page.click("#receiveBank")
    hector.until("bank.length===32", timeout=8000)
    hector.idle()
    hector.page.click("#sendBank")
    hector.wait(500)
    assert hector.synth("S.invalidSends") == 0
    assert hector.errors == []


# ------------------------------------- 4. Les autres chemins d'ecriture (v1.10)

def _first_index(hector, cond):
    return hector.synth(f"S.log.findIndex(m=>{cond})")


def test_active_bank_preview_writes_then_plays(hector):
    """Preecoute d'un preset de la banque : il est ecrit dans son programme, puis la melodie joue."""
    hector.connect()
    d = preset_payload(11, "PREVIEW_")
    hector.js("window.__synth.log=[]")
    hector.js("d=>{window.__it={rank:6,name:'P',data:new Uint8Array(d)};playPresetMidiPreview(window.__it)}", d)
    hector.until("window.__synth.log.some(m=>(m[0]&0xF0)===0x90&&m[2]>0)", timeout=6000, what="la premiere note")
    assert hector.synth("S.progs[5]") == d
    write = _first_index(hector, "m.length===75&&m[7]===0x15")
    note = _first_index(hector, "(m[0]&0xF0)===0x90&&m[2]>0")
    assert 0 <= write < note, "La melodie a commence avant la fin de l'ecriture"
    hector.js("stopPresetMidiPreview()")


def test_stop_during_preview_write_plays_nothing(hector):
    hector.connect()
    hector.js("window.__synth.log=[]")
    hector.js("d=>{window.__it={rank:6,name:'P',data:new Uint8Array(d)};playPresetMidiPreview(window.__it)}", preset_payload(12))
    hector.wait(150)
    hector.js("vpGlobalStop();stopPresetMidiPreview()")
    hector.wait(3000)
    assert hector.synth("S.log.filter(m=>(m[0]&0xF0)===0x90&&m[2]>0).length") == 0, "Une melodie a joue apres Stop"


def test_library_preview_restores_program(hector):
    """Preecoute depuis la bibliotheque : le programme d'ecoute est emprunte, puis rendu intact."""
    hector.connect()
    prog = hector.js("AUDITION_PROGRAM") - 1
    original = hector.synth(f"S.progs[{prog}].slice()")
    d = preset_payload(13, "LIBRARY_")
    hector.js("d=>{window.__lib={name:'L',data:new Uint8Array(d)};auditionLibraryPreset(window.__lib,window.__lib.data)}", d)
    hector.until("!!activePresetMidiPreview", timeout=10000, what="le debut de la melodie")
    assert hector.synth(f"S.progs[{prog}]") == d, "Le preset de la bibliotheque n'a pas ete charge"
    hector.js("stopPresetMidiPreview()")
    hector.idle(timeout=15000)
    assert hector.synth(f"S.progs[{prog}]") == original, "Le programme d'ecoute n'a pas ete restaure"
    assert "restored" in hector.status()


def test_send_linked_preset(hector):
    """Bouton d'envoi d'un preset de la banque active : ecrit, relu, marque synchronise."""
    hector.connect()
    hector.page.click("#receiveBank")
    hector.until("bank.length===32", timeout=8000)
    hector.idle()
    hector.js("(()=>{const i=bank.find(i=>items[i].rank===4);const it=items[i];it.data=new Uint8Array(it.data);it.data[1]=77;selectedSet.clear();selectedSet.add(i);selected=i;render()})()")
    hector.page.click("#sendPreset")
    hector.until("window.__synth.progs[3][1]===77", timeout=8000, what="l'ecriture du preset 4")
    hector.idle()
    assert "written to the synth and checked" in hector.status()


def test_write_without_midi_input(hector):
    """Sans entree MIDI, l'ecriture part quand meme, mais Hector dit qu'elle n'est pas verifiee."""
    hector.connect()
    hector.js("midiIn.onmidimessage=null;midiIn=null")
    d = preset_payload(14, "NOINPUT_")
    hector.js("d=>{window.__it={rank:8,name:'N',data:new Uint8Array(d)};sendPresetDataToSynth(window.__it,window.__it.data)}", d)
    hector.idle()
    assert hector.synth("S.progs[7]") == d
    assert "not confirmed" in hector.status()


# ------------------------------------------------------------------ 5. Patterns

def test_read_pattern_bank(hector):
    hector.connect()
    hector.js("startPatternReceive('bank')")
    hector.until("!patternReceiveMode", timeout=8000, what="la fin de la lecture des patterns")
    got = hector.js("vp2State.synthBank.map(s=>s.lastReceivedData)")
    assert got == hector.synth("S.pats")
    assert hector.errors == []


def test_send_pattern_bank(hector):
    hector.connect()
    payload = [(i * 7) % 127 for i in range(2048)]
    ok = hector.js("p=>sendPatternMessage(makePatternMessage(PATTERN_BANK_CMD,new Uint8Array(p)),'bank',{skipConfirm:true})", payload)
    assert ok is True
    hector.until("window.__synth.writes>0", timeout=4000)
    hector.wait(200)
    assert hector.synth("S.pats.flat()") == payload
    assert hector.synth("S.badChecksums") == 0


def test_pattern_send_blocked_when_synth_not_listening(hector):
    hector.js("window.__synth.listening=false")
    hector.connect()
    hector.js("window.__synth.writes=0")  # la verification du synthe a la connexion fait une ecriture de test
    before = hector.synth("S.pats.map(p=>p.slice())")
    ok = hector.js("()=>sendPatternMessage(makePatternMessage(PATTERN_BANK_CMD,new Uint8Array(2048)),'bank',{skipConfirm:true})")
    assert ok is False
    hector.wait(300)
    assert hector.synth("S.writes") == 0, "Un envoi bloque est quand meme parti"
    assert hector.synth("S.pats") == before
    assert "blocked" in hector.status()


# ------------------------------------------------------------ 6. Stockage refuse

def test_app_works_when_storage_is_refused(browser, hector_path, script_runs):
    """Navigation privee stricte : le navigateur refuse localStorage. Hector doit fonctionner quand meme."""
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script("""(()=>{const deny=()=>{throw new DOMException('denied','SecurityError')};
      Object.defineProperty(window,'localStorage',{get:deny,configurable:true});
      Object.defineProperty(window,'sessionStorage',{get:deny,configurable:true})})()""")
    page.goto(hector_path.as_uri())
    page.wait_for_timeout(1500)
    assert page.evaluate("()=>typeof vpAlert==='function' && prefGet('vectorpatch.theme','light')==='light' && prefSet('x','1')===false")
    assert errors == []
    page.close()
