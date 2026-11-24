#!/usr/bin/env python3
"""Recalcule l'empreinte CSP du script de Hector the Manager.

Usage : python3 update_csp.py Hector_the_Manager_v1.9.1.html
A lancer apres chaque modification du code JavaScript.
"""
import base64, hashlib, re, sys

if len(sys.argv) != 2:
    sys.exit("Usage : python3 update_csp.py <fichier.html>")

path = sys.argv[1]
html = open(path, encoding="utf-8").read()

scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
if len(scripts) != 1:
    sys.exit(f"Erreur : {len(scripts)} blocs <script> trouves, 1 attendu.")

digest = base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode()
new_html, n = re.subn(r"script-src 'sha256-[^']+'", f"script-src 'sha256-{digest}'", html)
if n != 1:
    sys.exit("Erreur : ligne CSP introuvable dans le fichier.")

if new_html == html:
    print("Empreinte deja a jour, rien a faire.")
else:
    open(path, "w", encoding="utf-8").write(new_html)
    print(f"Empreinte mise a jour : sha256-{digest}")
