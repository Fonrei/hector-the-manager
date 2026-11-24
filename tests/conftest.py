"""Reglages communs des tests : quel fichier tester, quel navigateur, et la page preparee."""
import os
import pathlib
import pytest
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent


def pytest_addoption(parser):
    parser.addoption("--hector", action="store", default=os.environ.get("HECTOR_HTML"),
                     help="Chemin du fichier Hector_the_Manager_*.html a tester")
    parser.addoption("--chrome", action="store", default=os.environ.get("CHROME_PATH"),
                     help="Chemin de Chrome (facultatif ; sinon le Chromium de Playwright)")


@pytest.fixture(scope="session")
def hector_path(pytestconfig):
    p = pytestconfig.getoption("--hector")
    if not p:
        pytest.exit("Indique le fichier a tester : --hector Hector_the_Manager_v1.9.3.html", 2)
    p = pathlib.Path(p).expanduser().resolve()
    if not p.exists():
        pytest.exit(f"Fichier introuvable : {p}", 2)
    return p


@pytest.fixture(scope="session")
def browser(pytestconfig):
    chrome = pytestconfig.getoption("--chrome")
    with sync_playwright() as pw:
        kw = {"executable_path": chrome} if chrome else {}
        b = pw.chromium.launch(args=["--no-sandbox"], **kw)
        yield b
        b.close()


class Hector:
    """Une page Hector chargee avec le faux synthe, plus quelques raccourcis."""

    def __init__(self, page):
        self.page = page
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: self.errors.append("console: " + m.text) if m.type == "error" else None)

    def js(self, code, arg=None):
        return self.page.evaluate(code, arg)

    def wait(self, ms):
        self.page.wait_for_timeout(ms)

    def until(self, expr, timeout=8000, what=None):
        """Attend qu'une expression JS devienne vraie. (Le CSP d'Hector interdit
        wait_for_function de Playwright, qui passe par eval : c'est voulu.)"""
        import time
        end = time.monotonic() + timeout / 1000
        while time.monotonic() < end:
            if self.js(f"()=>!!({expr})"):
                return
            self.page.wait_for_timeout(50)
        raise AssertionError(f"Delai depasse en attendant : {what or expr}")

    def status(self):
        return self.js("document.getElementById('statusText').textContent")

    def alerts(self):
        return self.js("window.__alerts.slice()")

    def synth(self, expr):
        return self.js(f"(()=>{{const S=window.__synth;return {expr}}})()")

    def connect(self, check=True):
        """Ouvre le MIDI ; si check, attend la fin de la verification automatique du synthe."""
        self.page.click("#refreshMidi")
        self.until("typeof midiOut!=='undefined' && !!midiOut && !!midiIn", timeout=5000)
        if check:
            self.js("vpSynthCheck.running || vpSynthCheck.listening===true || vpCheckSynth()")
            self.until("vpSynthCheck.listening!==null && !vpSynthCheck.running", timeout=15000)
            self.until("vpAuditionBusy===0", timeout=15000)

    def idle(self, timeout=15000):
        self.until("vpAuditionBusy===0 && !receiveMode && !patternReceiveMode", timeout=timeout)


@pytest.fixture(scope="session")
def script_runs(browser, hector_path):
    """Verifie une seule fois que le script d'Hector s'execute. Sinon, tous les
    tests de page echouent tout de suite avec un message clair."""
    page = browser.new_page()
    try:
        page.goto(hector_path.as_uri())
        page.wait_for_timeout(1500)
        if not page.evaluate("()=>typeof vpAlert==='function'"):
            pytest.fail("Le script d'Hector ne s'execute pas (empreinte CSP perimee ? erreur de syntaxe ?)", pytrace=False)
    finally:
        page.close()


@pytest.fixture
def hector(browser, hector_path, script_runs):
    page = browser.new_page()
    page.add_init_script(path=str(HERE / "fake_synth.js"))
    h = Hector(page)
    page.goto(hector_path.as_uri())
    h.until("typeof vpAlert==='function'")
    # Les boites de dialogue d'Hector sont remplacees : les alertes sont enregistrees,
    # les confirmations repondent "OK". On teste les donnees, pas les dialogues.
    h.js("""()=>{window.__alerts=[];
      vpAlert=(m)=>{window.__alerts.push(String(m))};
      vpConfirm=async()=>true;}""")
    yield h
    page.close()
