# multi-agent-qa

Un pipeline multi-agent (LangGraph + Claude API) qui pilote et analyse les
tests Playwright du projet **`maisoncarmenta-qa`** — orchestration, pas
duplication : ce projet ne contient aucun test lui-même.

## Comment les deux projets s'articulent

```text
../maisoncarmenta-qa/     <- les VRAIS tests Playwright (Page Objects,
                              fixtures, pytest.ini). Peut tourner seul,
                              sans ce projet.
./  (multi-agent-qa)      <- pilote maisoncarmenta-qa depuis l'extérieur :
                              lance pytest dessus, lit son rapport JUnit,
                              fait analyser les résultats par des agents
                              Claude, affiche tout dans une interface web.
```

Les deux dossiers doivent être **frères** (côte à côte, même dossier
parent) — `agents/executeur.py` référence `maisoncarmenta-qa` par un
chemin relatif (`../maisoncarmenta-qa`).

## Le pipeline

```text
Superviseur (LangGraph, pattern Supervisor)
  ├─ Analyste   : suggestions de couverture depuis une spec — jamais exécutées
  ├─ Exécuteur  : lance `pytest` sur la VRAIE suite (pas de génération de code)
  ├─ Triage     : catégorise les échecs réels et les tests flaky (via rerun)
  └─ Rapporteur : synthèse finale (résultats + suggestions, jamais mélangés)
```

Historique court : une première version générait du code Playwright à la
volée depuis des cas de test suggérés. Abandonné — le code généré ne
respectait pas systématiquement le Page Object Model et produisait plus de
faux échecs que de vrais signaux. Le pivot actuel exécute la vraie suite.

## Installation (une fois)

```powershell
cd multi-agent-qa
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env   # coller ta clé ANTHROPIC_API_KEY
```

`maisoncarmenta-qa` doit avoir son propre environnement déjà installé (voir
son propre README) — `agents/executeur.py` utilise directement
`maisoncarmenta-qa/.venv/Scripts/python.exe`.

## Lancer

**Interface web (recommandé)** : double-clique sur `demarrer.bat`. Ouvre
automatiquement `http://127.0.0.1:8000` après le démarrage du serveur.

**Ligne de commande** :

```powershell
.venv\Scripts\python.exe main.py "spécification optionnelle en français"
.venv\Scripts\python.exe main.py "" --tests "tests/test_homepage.py::test_homepage_loads[chromium]"
```

## Coût

Chaque lancement fait de vrais appels à l'API Claude (Opus 5) — pas de mode
gratuit. L'interface affiche une estimation avant de lancer, mais c'est un
ordre de grandeur, pas une facture exacte.

## Structure

```text
agents/         un fichier par agent (analyste, executeur, triage, rapporteur)
orchestrator/   state.py (contrat de données), supervisor.py, graph.py, runner.py
schemas/        modèles Pydantic partagés entre agents
web/            interface (servie par server.py)
server.py       API FastAPI + sert l'interface
main.py         point d'entrée CLI
reports/        généré à chaque run (JUnit XML, historique) — jamais committé
```
