# Utvikling

Bruk korte feature branches og pull request mot `main`. CI validerer kildekode uten å kontakte Fabric. Etter merge deployes samme commit til DEV; test og prod får kun eksplisitt promotering av den pinnede DEV-commiten.

## Profilendringer

Legg til en profil ved å opprette config- og parameterfil, og registrere den eksplisitt i `config/profiles.yml`. Ikke stol på filnavn alene for å aktivere deploy.

## Selektiv deploy

Den profilavgrensede diff-logikken inkluderer rapporter som avhenger av en endret semantisk modell. Uklare rapportbindinger inkluderes som sikkerhetsfallback. Endres config eller parameterfil, velges full deploy.

Ved tvil om git-baseline: kjør full deploy. Dette er tryggere enn å risikere å utelate en artefakt.
