# pbip-template

Copier-template for generiske Power BI PBIP-prosjekter med Microsoft Fabric, `fabric-cicd` og Azure DevOps.

## Hva den genererer

- Explicit profile manifest og miljøspesifikke workspace-ID-er
- Sikker standard for orphan cleanup (`unpublish.skip: true`)
- Valgbar CI-autentisering: Azure CLI/service connection, client secret eller managed identity
- PR-validering, automatisk DEV-deploy og manuelt godkjent promotering
- Valgfri, policy-styrt refresh av semantiske modeller
- Konservativ selektiv deploy som kan aktiveres med eksplisitt git-baseline

## Generer prosjekt

```powershell
copier copy <template-repo-url> <target-folder> --trust
```

`--trust` er nødvendig fordi Copier oppretter virtualenv, initialiserer Git og lager initial commit. Se generert `docs/setup.md` før du oppretter en service connection eller pipeline.
