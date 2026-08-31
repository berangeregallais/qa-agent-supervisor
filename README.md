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

## Tests (des agents eux-mêmes, pas de maisoncarmenta.com)

```powershell
.venv\Scripts\python.exe -m pytest -v
```

61 tests, aucun appel Claude réel ni sous-processus pytest réel — tout ce
qui touche l'API Anthropic ou un vrai `pytest` est mocké (`unittest.mock`).
Ce qui est couvert :

- **Logique pure** : parsing JUnit XML, lecture du compteur de reruns,
  construction de l'état initial, persistance du "dernier run".
- **Décision déterministe du Triage** : un test récupéré après rerun est
  catégorisé "flaky" par preuve directe, sans jamais appeler Claude — testé
  en vérifiant qu'aucun mock d'API n'est nécessaire pour ce cas précis.
- **Câblage des agents qui appellent Claude** (Analyste, Superviseur,
  Triage sur échec persistant, Rapporteur) : le client Anthropic est mocké,
  on vérifie que la décision/sortie simulée est correctement intégrée dans
  le state — pas la qualité de la décision elle-même (voir "Pistes
  d'évolution").
- **L'API FastAPI** via `TestClient` : cycle de vie complet d'un run
  (running → done/error/cancelled), 404 sur un run inconnu, réactivité de
  l'annulation pendant qu'un run "long" est simulé en cours.

## Structure

```text
agents/         un fichier par agent (analyste, executeur, triage, rapporteur)
orchestrator/   state.py (contrat de données), supervisor.py, graph.py, runner.py
schemas/        modèles Pydantic partagés entre agents
tests/          tests des agents eux-mêmes (voir "Tests" ci-dessus)
web/            interface (servie par server.py)
server.py       API FastAPI + sert l'interface
main.py         point d'entrée CLI
reports/        généré à chaque run (JUnit XML, historique) — jamais committé
```

## Pistes d'évolution

- **Évaluation LangSmith** — la suite pytest ci-dessus vérifie que les
  agents sont bien *câblés* (le state circule correctement), mais pas que
  leurs décisions LLM sont *bonnes* (le Superviseur route-t-il
  correctement dans un cas ambigu ? les suggestions de l'Analyste sont-
  elles pertinentes ?). `langsmith.evaluate()` est fait pour ça : faire
  tourner un agent sur un jeu d'exemples et noter la qualité des réponses,
  avec suivi dans le temps. Nécessite un compte LangSmith séparé et un
  vrai jeu d'exemples de référence — volontairement pas fait aujourd'hui
  pour ne pas bâcler ni le jeu d'exemples ni la suite pytest existante.
- **Historique des runs** (SQLite ou JSON horodaté par run) pour calculer
  un vrai taux de flakiness dans le temps, pas seulement sur un run isolé.
- **Rapporteur multi-niveaux** : un résumé différent selon le lecteur (dev
  vs décideur).
- **Agent Validateur** (vérifier qu'une assertion peut réellement échouer)
  et **Agent Data** (V2, cycle de vie des données de test) — évoqués dans
  l'architecture mais jamais implémentés.
- CI GitHub Actions, notifications Slack/email sur détection d'un vrai
  `bug_produit`, coût cumulé suivi dans le temps.
