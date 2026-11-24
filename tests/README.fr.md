# Tests automatiques de Hector the Manager

Ces tests ouvrent Hector dans Chrome, branchent un **faux Pro VS Mini** (`fake_synth.js`) à la place du vrai, et vérifient que les fonctions critiques marchent. Il y a 42 tests, et la suite prend environ une minute et demie. Ton vrai synthé n'est jamais touché.

## Installation (une seule fois)

Il faut Python 3, puis :

```
python3 -m pip install pytest playwright
python3 -m playwright install chromium
```

## Lancer les tests

Depuis ce dossier :

```
python3 run_tests.py ../Hector_the_Manager_v1.9.3.html
```

Si tu préfères utiliser ton Chrome déjà installé plutôt que le Chromium de Playwright, ajoute `--chrome "/chemin/vers/chrome"`.

Le résultat se lit sur la dernière ligne :

- `42 passed` : tout va bien.
- `FAILED test_…` : quelque chose a cassé. Le nom du test et le message disent quoi.

## Ce qui est vérifié

**Le fichier lui-même**
- L'empreinte CSP correspond au script. Sinon la page est morte, et la suite s'arrête en 2 secondes avec un message clair.
- La politique de sécurité bloque toujours tout accès réseau.
- Le numéro de version est le même partout (titre, en-tête, pied de page, « À propos »).
- La page se charge sans erreur, et ne consomme presque rien au repos.

**Les formats SysEx et les imports**
- Les messages preset, banque et pattern ont le bon format et la bonne somme de contrôle.
- Un preset fait l'aller-retour export → import à l'identique.
- Les fichiers preset et banque corrompus sont refusés (somme de contrôle fausse, octet > 127).
- Les sauvegardes JSON invalides sont refusées (octet > 127, identifiant faux, slot manquant…).

**Les échanges avec le synthé (simulé)**
- Les ports PROVS-MINI sont choisis automatiquement à la connexion.
- La vérification du synthé ne laisse aucune trace, détecte un synthé qui n'écoute pas, et prévient si elle est interrompue.
- L'écriture d'un preset est relue. Un preset ignoré par le synthé n'est pas marqué comme synchronisé.
- La lecture d'un preset et d'une banque depuis le synthé fonctionne, et une réponse corrompue est refusée.
- L'envoi d'une banque complète arrive intact.
- Après Stop, aucune note ne reste enfoncée.
- Aucun message MIDI invalide n'est jamais envoyé.
- La préécoute d'un preset de la banque écrit d'abord le preset, puis joue la mélodie ; un Stop pendant l'écriture empêche la mélodie.
- La préécoute depuis la bibliothèque emprunte le programme d'écoute, puis le rend intact.
- L'envoi d'un preset lié à la banque est écrit et relu.
- Sans entrée MIDI, l'écriture part, et Hector dit qu'elle n'est pas vérifiée.

**Les patterns**
- La lecture des 16 patterns du synthé et l'envoi d'une banque de patterns arrivent intacts.
- L'envoi est bloqué si le synthé n'écoute pas.

**Le navigateur**
- Hector fonctionne même si le navigateur refuse tout stockage (navigation privée stricte).

## Ce que les tests ne remplacent pas

Le faux synthé suit le protocole tel qu'Hector le comprend. Si le vrai Pro VS Mini se comportait autrement (nouveau firmware, par exemple), seul un essai avec le vrai synthé le montrerait. Après une modification importante, fais donc toujours un essai rapide avec le synthé : connexion, lecture d'un preset, écriture d'un preset.

## Fichiers

- `run_tests.py` : le lanceur.
- `test_hector.py` : les tests.
- `fake_synth.js` : le faux Pro VS Mini, pilotable depuis les tests via `window.__synth`.
- `conftest.py` : le chargement de la page et les raccourcis communs.
- `pytest.ini` : la configuration de pytest.
