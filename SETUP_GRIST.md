# Création du compte de service Grist
Assurez-vous de remplacer `${GRIST_PERSONAL_API_KEY}` par votre clé d'API Grist.
```bash
export GRIST_PERSONAL_API_KEY=votre_cle_api_personnelle
```

## Lister les comptes de service existants

```bash
curl -X GET "https://grist.francedatareseau.fr/api/service-accounts" \
-H "Authorization: Bearer ${GRIST_PERSONAL_API_KEY}" \
-H "Content-Type: application/json"
```

## Créer un nouveau compte de service

```bash 
curl -X POST "https://grist.francedatareseau.fr/api/service-accounts" \
-H "Authorization: Bearer ${GRIST_PERSONAL_API_KEY}" \
-H "Content-Type: application/json" \
-d '{"label":"FDR TCD", "description":"application TCD - lecture et écriture", "expiresAt":"2040-10-10"}'
```

Bien noter le contenu des champs `login`et `key`de la réponse, car ils ne seront pas affichés à nouveau. 
Ils devront être stockés dans un fichier `.env` ou en tant que secrets sur github pour les utiliser dans l'application.