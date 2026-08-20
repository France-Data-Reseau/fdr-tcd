# Sécurité — plan anti-exfiltration et checklist

> Révisé suite aux revues du 2026-06-12 (`revues/`) : périmètre étendu aux lectures (B2),
> sessions précisées (S5), headers répartis (S6), CSP fondée sur l'inventaire réel des
> templates (S7), URLs validées (S8), sauvegarde et clé API (D1/D2), RGPD (R4).

## 1. « Pas de faille permettant de siphonner les données Grist »

Le « joyau » est la clé API Grist (lecture/écriture totale du document). Vecteurs
d'exfiltration et verrous :

| Vecteur | Verrou |
|---|---|
| Vol de la clé API | Elle ne vit que dans `repositories/grist_session.py` côté serveur ; jamais dans le front, les logs, ni les messages d'erreur (erreurs Grist reformulées sans URL ni doc ID — la v1 loguait l'URL complète à chaque requête) |
| Endpoint « proxy » trop générique | Aucun n'existe : pas de route qui relaie une table/colonne arbitraire vers Grist. Chaque réponse est construite **champ par champ en liste blanche** dans les services |
| `/api/restitution/donnees` aspiré par un compte Visiteur | Session obligatoire (401 sinon), payload limité aux champs v1 — **les contacts (emails/téléphones) n'y figurent pas**, comme en v1 ; rate limiting modéré ; `Cache-Control: private` |
| IDOR en **écriture** (forger des IDs hors périmètre) | Dépendance `require_ownership` centralisée sur toutes les routes d'écriture paramétrées, **sous-objets compris** (la v1 ne couvrait que la collectivité) |
| IDOR en **lecture** (B2 — énumérer des IDs en GET pour reconstituer l'annuaire des contacts affiché par les pages de complétion) | `require_ownership` s'applique **aussi aux GET paramétrés de complétion** (`/collectivite/{id}`, `/projet/{id}`, sous-objets) pour les Éditeurs — Administrateur exempté. Réponse hors périmètre : **404** (uniformise existant/inexistant, freine l'énumération ; un 403 confirmerait l'existence de l'ID). Testé dans `test_idor.py`, cas GET et POST |
| Création de comptes en masse → accès Visiteur | Inscription rate-limitée + validation admin obligatoire (`En attente` ne voit rien) |
| Injection via formulaires | Pydantic strict : seuls les champs attendus sont transmis ; champs formule jamais écrits ; noms de tables = constantes internes |
| XSS stocké via champs URL (`href="javascript:…"`) | Tout champ URL ressorti en lien (site web, url partenaire, document en ligne, info programme) validé `HttpUrl` http/https par Pydantic (S8) |
| Session volée/forgée | Cookies signés `Secure`/`HttpOnly`/`SameSite=Lax`, `SECRET_KEY` obligatoire en prod, expiration glissante 1 h, régénération à la connexion |
| XSS → vol de session | Jinja autoescape + `esc()` côté JS (acquis v1) + CSP stricte (voir §2-S7) |

## 2. Faiblesses v1 → réponses V2 (SECURITE_NOTES.md, enrichies par les revues)

| # | Faiblesse v1 | Réponse V2 |
|---|---|---|
| 1 | Pas de rate limiting | slowapi : inscription, élévation, API restitution. **Derrière Caddy (S3)** : uvicorn lancé avec `--proxy-headers --forwarded-allow-ips=<réseau docker>`, key function slowapi sur l'IP transmise — sinon les limites seraient globales (un abuseur épuiserait le quota de tous). Testé avec `X-Forwarded-For` |
| 2 | Énumération d'emails au login | Réponses neutres au login **et à l'inscription** |
| 3 | Anti-IDOR au cas par cas | `require_ownership` centralisé : écritures ET lectures paramétrées de complétion, sous-objets compris ; 404 hors périmètre |
| 4 | Validation minimale (`form.get` partout) | Pydantic par formulaire (`services/types.py`), `HttpUrl` pour les champs URL |
| 5 | Pas de CSP | CSP stricte **après assainissement complet** : inventaire réel des templates v1 = 5 blocs `<script>` inline + 1 handler `onclick` (base, accueil, cas_usage, restitution ×2) → tous externalisés vers `static/js/` ; Leaflet auto-hébergé ; tuiles carto = OpenStreetMap → `img-src` autorise `https://*.tile.openstreetmap.org` (S7). + X-Content-Type-Options, Referrer-Policy |
| 6 | Logs verbeux (doc ID, emails) | Logger sobre : pas de doc ID, pas d'emails en clair évitables |
| 7 | Pas de timeout/retry homogènes | `requests.Session` unique : timeout global, retries bornés, `pool_maxsize ≥ 8` (lectures parallèles), erreurs propres |
| 8 | `SECRET_KEY` régénérée si absente | Refus de démarrer en production sans `SECRET_KEY`. Rotation possible : liste de clés (nouvelle + ancienne) |
| 9 | Pas de tests de sécurité | Tests dédiés : accès, IDOR (GET+POST), CSRF, headers, rate limit, jetons (voir 04_TESTS.md) |
| 10 | Géocodage non borné | Timeout 10 s + échec géocodage ≠ échec de page |

**Propriété des headers (S6)** — deux émetteurs de CSP s'intersectent et cassent
sournoisement. Répartition : **CSP, X-Content-Type-Options, Referrer-Policy = l'app**
(qui connaît ses scripts) ; **HSTS = Caddy** (qui termine TLS). Le contenu réel du snippet
`security_headers` du Caddyfile du stack sera vérifié avant le premier `up`.

**Sessions (S5)** — les cookies signés ne se révoquent pas côté serveur. La session ne
stocke donc que **l'identité (email + id Grist)** ; le **rôle est re-résolu à chaque
requête** via le repository utilisateurs (cache 5 min) → toute rétrogradation/désactivation
par l'admin prend effet en ≤ 5 min. Expiration glissante 1 h.

## 3. Droits — vocabulaire français (décision Victor)

- L'app utilise **exclusivement** les 5 valeurs françaises : `Administrateur`, `Editeur`,
  `Visiteur`, `Extention`, `En attente` — constante unique `DROITS` dans `services/types.py`.
- `Extention` est une coquille **présente dans les données Grist** : commentaire explicite
  à côté de la constante (« ne pas corriger l'orthographe : valeur de données ») pour
  qu'aucun correctif bien intentionné ne casse les contrôles d'accès (R6).
- L'app n'écrit **jamais** de valeur anglaise ; les valeurs héritées (`Administrator`,
  `Editor`, `Viewer`, `Pending`) sont normalisées à la lecture et réécrites en français à
  la prochaine mise à jour du record.
- **Option sur accord de Victor** : nettoyage one-shot via l'API (jamais l'interface —
  piège n°1). Le script sera **dry-run par défaut** (liste des records impactés), exécution
  réelle sur double confirmation, et **précédé d'un export du document Grist** (voir §5).

## 4. Données et exploitation (D1, D2, R4)

- **Sauvegarde Grist (D1)** : l'app détient une clé en écriture totale et pratique le PATCH
  par lots — un bug peut corrompre la seule source de données. Avant le go-live et avant
  tout script one-shot : **export daté du document** (snapshot natif Grist + téléchargement
  `.grist`/xlsx via l'API — script `scripts/export_grist.py`). Idéalement : export
  périodique conservé hors VPS. **→ qui déclenche / où stocker : Victor.**
- **Clé API (D2)** : recommandation = **compte de service dédié**, accès limité à ce seul
  document (pas une clé personnelle/admin de l'instance), procédure de rotation écrite au
  README. **→ à confirmer par Victor** (la clé v1 est-elle déjà un compte de service ?).
- **RGPD (R4)** : emails/téléphones de contacts et comptes utilisateurs = données
  personnelles. À prévoir : mentions légales + politique de confidentialité (page statique),
  durée de rétention des comptes « En attente » jamais validés, et confirmation que le
  sous-objet « document » est bien un **lien** (pas d'upload de fichier — c'est le cas en
  v1, le champ `Document_fichier_` Attachments de Grist n'est pas exposé par l'app).

## 5. Matrice des droits (rappel, identique v1)

| Rôle | Cartographie | Complétion | Admin |
|---|---|---|---|
| Administrateur | ✅ | ✅ toutes collectivités | ✅ |
| Editeur | ✅ | ✅ SA collectivité uniquement (lecture ET écriture) | ❌ |
| Visiteur | ✅ | ❌ (bouton grisé + demande d'élévation) | ❌ |
| Extention | ✅ | ❌ (demande en cours) | ❌ |
| En attente | ❌ (acces-refuse) | ❌ | ❌ |

Appliquée **côté serveur** (dépendances) ET côté affichage (templates).

## 6. Checklist de revue finale — ÉTAT AU 2026-06-13

1. ☑ Auth réelle en place (SSO OIDC + PKCE), `BDD_Utilisateurs` = référentiel des rôles
2. ☑ Sessions signées, cookies `Secure`/`HttpOnly`/`SameSite=Lax`, HSTS (Caddy), régénération à la connexion
3. ☑ CSRF vérifié sur 100 % des POST (test automatisé)
4. ☑ Anti-IDOR centralisé : écritures ET lectures paramétrées, sous-objets compris, 404 hors périmètre (tests verts)
5. ☑ Rate limiting : inscription, élévation, API restitution (IP) — `--proxy-headers` posé ; ☐ reste un test réel `X-Forwarded-For` en prod
6. ☑ Réponses neutres au login ET à l'inscription (pas d'énumération d'emails)
7. ☑ Validation Pydantic sur chaque formulaire, `HttpUrl` sur les champs URL
8. ☑ CSP stricte (zéro script inline ; `unsafe-inline` styles seulement — justifié, voir revues/AUDIT_ARCHITECTURE.md §5), X-Content-Type-Options, Referrer-Policy — un seul émetteur par header
9. ☑ Clé API jamais dans les logs/front/erreurs ; logs sobres ; ☐ compte de service dédié : EN ATTENTE (clé v1 réutilisée, demande à faire à FDR)
10. ☑ Refus de démarrage en prod sans `SECRET_KEY` ; `debug=False`
11. ☑ Timeouts/retries Grist + api-adresse ; aucune stacktrace côté utilisateur
12. ☑ Conteneur non-root, port 8000 jamais publié, `.env` chmod 600, aucune donnée réelle dans les fixtures
13. ☑ SMTP non bloquant pour l'auth (notifications admin uniquement)
14. ☑ Export/snapshot Grist daté réalisé (2026-06-12, sur le VPS) ; ☐ sauvegarde PÉRIODIQUE + copie hors VPS : à organiser (action Victor)
15. ☑ Limites de ressources + rotation des logs posées ; SHA visible dans `/health`
16. ☑ Mono-worker verrouillé (CMD sans `--workers`, AGENTS.md/MAINTENANCE.md)
17. ☐ **Mentions légales / politique de confidentialité : NON FAITES** (texte à fournir par Victor — données personnelles en prod, à traiter rapidement)
